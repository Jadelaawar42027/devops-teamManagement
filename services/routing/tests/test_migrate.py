from contextlib import closing

import pymssql
import pytest
from conftest import MIGRATIONS_DIR

import db
from migrate import applied_versions, migration_files, run_migrations, split_batches

# --- pure helpers, no database ---


def test_split_batches_on_go_lines_only():
    sql = "ALTER TABLE t ADD c INT;\nGO\nUPDATE t SET c = 1; -- GOOD\n  go  \n\n"
    assert split_batches(sql) == ["ALTER TABLE t ADD c INT;", "UPDATE t SET c = 1; -- GOOD"]


def test_migration_files_sorted_and_filtered(tmp_path):
    for name in ["002_b.sql", "001_a.sql", "notes.txt", "1_bad.sql"]:
        (tmp_path / name).write_text("SELECT 1")
    assert migration_files(tmp_path) == ["001_a.sql", "002_b.sql"]


def test_duplicate_numbers_rejected(tmp_path):
    (tmp_path / "001_a.sql").write_text("SELECT 1")
    (tmp_path / "001_b.sql").write_text("SELECT 1")
    with pytest.raises(RuntimeError):
        migration_files(tmp_path)


# --- against a fresh, empty SQL Server database each ---


@pytest.fixture
def fresh_conn(make_database, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", make_database("routing_migrate"))
    with closing(db.get_connection()) as conn:
        yield conn


def table_names(conn):
    cur = conn.cursor()
    cur.execute("SELECT name FROM sys.tables")
    return {row["name"] for row in cur.fetchall()}


def test_real_migrations_run_once_and_a_second_run_applies_nothing(fresh_conn):
    files = migration_files(MIGRATIONS_DIR)
    assert run_migrations(fresh_conn, MIGRATIONS_DIR) == files
    assert {"leads", "lead_outcomes", "schema_migrations"} <= table_names(fresh_conn)
    # the second boot: everything is recorded, so nothing runs again
    assert run_migrations(fresh_conn, MIGRATIONS_DIR) == []
    assert applied_versions(fresh_conn) == set(files)


def test_later_migration_changes_a_table_that_holds_data(fresh_conn, tmp_path):
    # the same shape as a real 002: add a column in one batch, backfill it in the next (GO)
    (tmp_path / "001_init.sql").write_text("CREATE TABLE things (id INT PRIMARY KEY, name NVARCHAR(50) NOT NULL);")
    run_migrations(fresh_conn, tmp_path)
    cur = fresh_conn.cursor()
    cur.execute("INSERT INTO things (id, name) VALUES (1, 'kept')")
    fresh_conn.commit()
    (tmp_path / "002_add_label.sql").write_text(
        "ALTER TABLE things ADD label NVARCHAR(50) NULL;\nGO\nUPDATE things SET label = CONCAT('#', id);\n"
    )
    assert run_migrations(fresh_conn, tmp_path) == ["002_add_label.sql"]
    cur.execute("SELECT id, name, label FROM things")
    assert cur.fetchall() == [{"id": 1, "name": "kept", "label": "#1"}]


def test_failing_migration_is_rolled_back_and_not_recorded(fresh_conn, tmp_path):
    (tmp_path / "001_init.sql").write_text("CREATE TABLE ok_table (id INT);")
    (tmp_path / "002_broken.sql").write_text("CREATE TABLE half_done (id INT);\nGO\nSELECT * FROM no_such_table;")
    with pytest.raises(pymssql.Error):
        run_migrations(fresh_conn, tmp_path)
    assert applied_versions(fresh_conn) == {"001_init.sql"}
    # the first batch of 002 was undone with the rest, so a fixed 002 can run cleanly next start
    assert "half_done" not in table_names(fresh_conn)
    assert "ok_table" in table_names(fresh_conn)

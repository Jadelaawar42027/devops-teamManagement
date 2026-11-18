import pytest

from migrate import migration_files, split_batches


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

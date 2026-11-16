import logging
import os
import re

log = logging.getLogger(__name__)

MIGRATION_FILE = re.compile(r"^(\d{3})_[a-z0-9_]+\.sql$")
# SQL Server compiles a whole batch before running it, so a column added with ALTER TABLE
# can only be used by a later batch. Migrations separate batches with a line containing only GO.
BATCH_SEPARATOR = re.compile(r"^\s*GO\s*$", re.IGNORECASE | re.MULTILINE)


def migration_files(folder):
    names = sorted(name for name in os.listdir(folder) if MIGRATION_FILE.match(name))
    numbers = [name[:3] for name in names]
    if len(numbers) != len(set(numbers)):
        raise RuntimeError("two migrations share a number: " + ", ".join(names))
    return names


def split_batches(sql):
    return [batch.strip() for batch in BATCH_SEPARATOR.split(sql) if batch.strip()]


def ensure_migrations_table(conn):
    cur = conn.cursor()
    cur.execute(
        """
        IF OBJECT_ID('dbo.schema_migrations', 'U') IS NULL
            CREATE TABLE schema_migrations (
                version NVARCHAR(255) NOT NULL PRIMARY KEY,
                applied_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
            )
        """
    )
    conn.commit()


def applied_versions(conn):
    cur = conn.cursor()
    cur.execute("SELECT version FROM schema_migrations")
    return {row["version"] for row in cur.fetchall()}


def run_migrations(conn, folder):
    ensure_migrations_table(conn)
    done = applied_versions(conn)
    applied_now = []
    for name in migration_files(folder):
        if name in done:
            continue
        with open(os.path.join(folder, name)) as f:
            batches = split_batches(f.read())
        cur = conn.cursor()
        try:
            # one transaction per file: SQL Server DDL is transactional, so a failing
            # migration leaves no half-applied schema and is retried on the next start
            for batch in batches:
                cur.execute(batch)
            cur.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (name,))
            conn.commit()
        except Exception:
            conn.rollback()
            log.error("migration %s failed, rolled back", name)
            raise
        log.info("applied migration %s", name)
        applied_now.append(name)
    if not applied_now:
        log.info("migrations up to date (%d applied)", len(done))
    return applied_now

import logging
import os
import time
from urllib.parse import unquote, urlparse

import pymssql

log = logging.getLogger(__name__)

# Azure SQL serverless returns 40613 ("database not currently available")
# while it resumes from auto-pause, which can take up to about a minute.
RETRY_ATTEMPTS = int(os.environ.get("DB_CONNECT_RETRIES", "8"))
RETRY_FIRST_DELAY_S = 1.0


def parse_database_url(url):
    # mssql://user:password@host:1433/database
    parts = urlparse(url)
    if parts.scheme != "mssql" or not parts.hostname or not parts.path.strip("/"):
        raise ValueError("DATABASE_URL must look like mssql://user:password@host:1433/database")
    return {
        "server": parts.hostname,
        "port": str(parts.port or 1433),
        "user": unquote(parts.username or ""),
        "password": unquote(parts.password or ""),
        "database": parts.path.strip("/"),
    }


def get_connection(attempts=None):
    settings = parse_database_url(os.environ["DATABASE_URL"])
    attempts = attempts or RETRY_ATTEMPTS
    delay = RETRY_FIRST_DELAY_S
    for attempt in range(1, attempts + 1):
        try:
            return pymssql.connect(
                server=settings["server"],
                port=settings["port"],
                user=settings["user"],
                password=settings["password"],
                database=settings["database"],
                login_timeout=15,
                timeout=30,
                as_dict=True,
                tds_version="7.4",
            )
        except pymssql.Error as exc:
            if attempt == attempts:
                raise
            log.warning("db connect failed (attempt %d/%d), retrying in %.0fs: %s", attempt, attempts, delay, exc)
            time.sleep(delay)
            delay = min(delay * 2, 15)


def fetch_all(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur.fetchall()


def fetch_one(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur.fetchone()


def execute(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    conn.commit()
    return cur.rowcount


def insert_returning_id(conn, sql, params=()):
    # sql must contain "OUTPUT INSERTED.id", since SQL Server has no lastrowid for pymssql
    cur = conn.cursor()
    cur.execute(sql, params)
    new_id = cur.fetchone()["id"]
    conn.commit()
    return new_id


def can_read_and_write(conn):
    # write a row inside a transaction and roll it back, so health proves write access without leaving data
    cur = conn.cursor()
    cur.execute("INSERT INTO schema_migrations (version) VALUES ('__health_probe__')")
    cur.execute("SELECT COUNT(*) AS n FROM schema_migrations")
    cur.fetchone()
    conn.rollback()

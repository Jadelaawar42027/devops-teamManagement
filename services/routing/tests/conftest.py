"""Database fixtures: tests that take `conn` or `client` run against a real SQL Server.

DATABASE_URL must point at a SQL Server login that may create databases (sa in the CI
service container, or a local throwaway container). The session creates a fresh database
with a random name, runs the real migrations into it, and drops it when the run ends, so
tests never touch a database that holds real data and two runs cannot collide.

Without DATABASE_URL the database tests are skipped and only the pure unit tests run.
"""

import os
import uuid
from contextlib import closing
from urllib.parse import urlparse, urlunparse

import pymssql
import pytest

import db
from migrate import run_migrations

SERVICE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MIGRATIONS_DIR = os.path.join(SERVICE_DIR, "migrations")
# emptied before each test; children before parents because of the foreign keys
TABLES = ["lead_outcomes", "leads"]
# no test creates this many rows, so this id never exists
MISSING_ID = 2_000_000_000

# read once at import: the session fixture later points DATABASE_URL at the test database
SERVER_URL = os.environ.get("DATABASE_URL")


def url_with_database(url, database):
    return urlunparse(urlparse(url)._replace(path="/" + database))


def server_connection():
    settings = db.parse_database_url(SERVER_URL)
    # autocommit: CREATE/DROP DATABASE cannot run inside a transaction
    return pymssql.connect(
        server=settings["server"],
        port=settings["port"],
        user=settings["user"],
        password=settings["password"],
        database="master",
        autocommit=True,
        login_timeout=15,
        tds_version="7.4",
    )


@pytest.fixture(scope="session")
def make_database():
    """Factory: make_database() creates an empty database and returns its DATABASE_URL."""
    if not SERVER_URL:
        pytest.skip("DATABASE_URL is not set: database tests need a SQL Server (see README)")
    created = []

    def make(prefix="routing_test"):
        name = f"{prefix}_{uuid.uuid4().hex[:10]}"
        with closing(server_connection()) as conn:
            conn.cursor().execute(f"CREATE DATABASE [{name}]")
        created.append(name)
        return url_with_database(SERVER_URL, name)

    yield make
    with closing(server_connection()) as conn:
        cur = conn.cursor()
        for name in created:
            # kick out any connection a failed test left open, then drop
            cur.execute(f"ALTER DATABASE [{name}] SET SINGLE_USER WITH ROLLBACK IMMEDIATE")
            cur.execute(f"DROP DATABASE [{name}]")


@pytest.fixture(scope="session")
def database_url(make_database):
    """One migrated database for the whole session; DATABASE_URL points at it meanwhile."""
    url = make_database()
    os.environ["DATABASE_URL"] = url
    with closing(db.get_connection()) as conn:
        run_migrations(conn, MIGRATIONS_DIR)
    yield url
    os.environ["DATABASE_URL"] = SERVER_URL


@pytest.fixture
def conn(database_url):
    """A connection to the session database, with every table emptied first."""
    connection = db.get_connection()
    cur = connection.cursor()
    for table in TABLES:
        cur.execute(f"DELETE FROM {table}")
    connection.commit()
    yield connection
    connection.close()


@pytest.fixture
def client(conn):
    """Flask test client on the same empty database. Migrations already ran in the session."""
    from app import create_app

    app = create_app(migrate=False)
    app.testing = True
    return app.test_client()

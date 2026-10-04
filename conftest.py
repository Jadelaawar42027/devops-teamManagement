import pytest

import db


@pytest.fixture
def conn(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    db.init_db()
    conn = db.get_connection()
    yield conn
    conn.close()

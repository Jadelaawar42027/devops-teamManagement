CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS members (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    role_id INTEGER NOT NULL REFERENCES roles(id),
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS kpi_definitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    metric TEXT NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS kpi_targets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kpi_id INTEGER NOT NULL REFERENCES kpi_definitions(id),
    member_id INTEGER NOT NULL REFERENCES members(id),
    year INTEGER NOT NULL,
    quarter INTEGER NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    target_value INTEGER NOT NULL CHECK (target_value >= 0),
    UNIQUE (kpi_id, member_id, year, quarter)
);

CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT,
    score INTEGER NOT NULL CHECK (score BETWEEN 0 AND 100),
    assigned_member_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS lead_outcomes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    lead_id INTEGER NOT NULL REFERENCES leads(id),
    outcome TEXT NOT NULL CHECK (outcome IN ('none', 'showing_booked', 'showing_performed', 'closed')),
    recorded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

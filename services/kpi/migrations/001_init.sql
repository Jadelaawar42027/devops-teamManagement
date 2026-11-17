-- KPI service schema, ported from the Assignment 1 SQLite schema.sql (kpi tables only)
CREATE TABLE roles (
    id INT IDENTITY(1,1) PRIMARY KEY,
    name NVARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE members (
    id INT IDENTITY(1,1) PRIMARY KEY,
    name NVARCHAR(200) NOT NULL,
    email NVARCHAR(255) NOT NULL UNIQUE,
    role_id INT NOT NULL REFERENCES roles(id),
    active BIT NOT NULL DEFAULT 1
);

CREATE TABLE kpi_definitions (
    id INT IDENTITY(1,1) PRIMARY KEY,
    role_id INT NOT NULL REFERENCES roles(id),
    name NVARCHAR(100) NOT NULL,
    metric NVARCHAR(50) NOT NULL,
    description NVARCHAR(500) NULL,
    CONSTRAINT uq_kpi_role_name UNIQUE (role_id, name)
);

CREATE TABLE kpi_targets (
    id INT IDENTITY(1,1) PRIMARY KEY,
    kpi_id INT NOT NULL REFERENCES kpi_definitions(id),
    member_id INT NOT NULL REFERENCES members(id),
    year INT NOT NULL,
    quarter INT NOT NULL CHECK (quarter BETWEEN 1 AND 4),
    target_value INT NOT NULL CHECK (target_value >= 0),
    CONSTRAINT uq_target UNIQUE (kpi_id, member_id, year, quarter)
);

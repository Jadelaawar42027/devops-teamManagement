-- Routing service schema, ported from the Assignment 1 SQLite schema.sql (routing tables only).
-- assigned_member_id is a member id owned by the KPI service: a plain INT with no foreign key,
-- since the members table lives in another database (ADR-3, ADR-7).
CREATE TABLE leads (
    id INT IDENTITY(1,1) PRIMARY KEY,
    source NVARCHAR(100) NOT NULL,
    score INT NOT NULL CHECK (score BETWEEN 0 AND 100),
    assigned_member_id INT NULL,
    assigned_at DATETIME2 NULL,
    created_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
);

CREATE TABLE lead_outcomes (
    id INT IDENTITY(1,1) PRIMARY KEY,
    lead_id INT NOT NULL REFERENCES leads(id),
    outcome NVARCHAR(30) NOT NULL CHECK (outcome IN ('none', 'showing_booked', 'showing_performed', 'closed')),
    recorded_at DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
);

CREATE INDEX ix_leads_assigned_member ON leads (assigned_member_id);
CREATE INDEX ix_outcomes_lead ON lead_outcomes (lead_id);

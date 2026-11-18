-- Leads get the name of the person enquiring. Existing rows are kept and backfilled
-- with a placeholder built from their id, then the column is made required.
-- Deploy only after the Azure database already holds leads (assignment §4.6).
ALTER TABLE leads ADD contact_name NVARCHAR(200) NULL;
GO
UPDATE leads SET contact_name = CONCAT('Lead #', id) WHERE contact_name IS NULL;
GO
ALTER TABLE leads ALTER COLUMN contact_name NVARCHAR(200) NOT NULL;

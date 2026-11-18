-- Local only: run by the one-off db-init service in docker-compose.yml.
-- Idempotent: every statement checks first, so it is safe on every `docker compose up`.
-- Each service gets its own database and its own login, and the login is a user only in
-- its own database, so kpi_svc cannot read routing's tables and vice versa.
-- db_owner is needed because each service runs its own migrations (CREATE/ALTER TABLE).
IF DB_ID('kpi') IS NULL CREATE DATABASE kpi;
GO
IF DB_ID('routing') IS NULL CREATE DATABASE routing;
GO
IF SUSER_ID('kpi_svc') IS NULL CREATE LOGIN kpi_svc WITH PASSWORD = '$(KPI_DB_PASSWORD)', CHECK_POLICY = OFF;
GO
IF SUSER_ID('routing_svc') IS NULL CREATE LOGIN routing_svc WITH PASSWORD = '$(ROUTING_DB_PASSWORD)', CHECK_POLICY = OFF;
GO
USE kpi;
IF USER_ID('kpi_svc') IS NULL CREATE USER kpi_svc FOR LOGIN kpi_svc;
ALTER ROLE db_owner ADD MEMBER kpi_svc;
GO
USE routing;
IF USER_ID('routing_svc') IS NULL CREATE USER routing_svc FOR LOGIN routing_svc;
ALTER ROLE db_owner ADD MEMBER routing_svc;
GO

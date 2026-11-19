"""Create or update each service's contained database user. Run by the CD pipeline only.

Connects to each Azure SQL database as the server admin and makes sure a user exists that
lives only inside that database (a "contained user", with its own password and no server
login), so kpi_svc can open the kpi database and nothing else, and the same for routing.
db_owner is needed because each service runs its own migrations (CREATE/ALTER TABLE).

Idempotent: a missing user is created, an existing one gets its password set again, so a
rotated GitHub secret takes effect on the next deploy.

All input comes from environment variables, set by the workflow from GitHub secrets and
Terraform outputs:
    SQL_SERVER_FQDN, SQL_ADMIN_LOGIN, SQL_ADMIN_PASSWORD,
    KPI_DATABASE, KPI_DB_PASSWORD, ROUTING_DATABASE, ROUTING_DB_PASSWORD
"""

import os
import sys
import time

import pymssql

USERS = [
    # (database env var, user name, password env var)
    ("KPI_DATABASE", "kpi_svc", "KPI_DB_PASSWORD"),
    ("ROUTING_DATABASE", "routing_svc", "ROUTING_DB_PASSWORD"),
]

# Passwords cannot be bound as parameters inside CREATE USER, so the statement is built in
# T-SQL from bound parameters: QUOTENAME(@user) wraps the name in [ ], and
# QUOTENAME(@password, '''') wraps the password in quotes and doubles any quote inside it,
# so neither value can break out of the statement.
ENSURE_USER = """
DECLARE @user sysname = %s, @password nvarchar(128) = %s, @sql nvarchar(max);
IF USER_ID(@user) IS NULL
    SET @sql = N'CREATE USER ' + QUOTENAME(@user) + N' WITH PASSWORD = ' + QUOTENAME(@password, '''');
ELSE
    SET @sql = N'ALTER USER ' + QUOTENAME(@user) + N' WITH PASSWORD = ' + QUOTENAME(@password, '''');
EXEC (@sql);
IF IS_ROLEMEMBER('db_owner', @user) = 0
BEGIN
    SET @sql = N'ALTER ROLE db_owner ADD MEMBER ' + QUOTENAME(@user);
    EXEC (@sql);
END
"""


def connect(database, attempts=8):
    # a paused serverless database refuses connections (error 40613) for up to about a minute
    delay = 2
    for attempt in range(1, attempts + 1):
        try:
            return pymssql.connect(
                server=os.environ["SQL_SERVER_FQDN"],
                port="1433",
                user=os.environ["SQL_ADMIN_LOGIN"],
                password=os.environ["SQL_ADMIN_PASSWORD"],
                database=database,
                login_timeout=30,
                tds_version="7.4",
            )
        except pymssql.Error as exc:
            if attempt == attempts:
                raise
            print(f"{database}: connect failed (attempt {attempt}/{attempts}), retrying in {delay}s: {exc}")
            time.sleep(delay)
            delay = min(delay * 2, 20)


def main():
    missing = [
        name for name in ["SQL_SERVER_FQDN", "SQL_ADMIN_LOGIN", "SQL_ADMIN_PASSWORD"] if not os.environ.get(name)
    ]
    missing += [name for db_var, _, pw_var in USERS for name in (db_var, pw_var) if not os.environ.get(name)]
    if missing:
        sys.exit("missing environment variables: " + ", ".join(missing))
    for db_var, user, pw_var in USERS:
        database = os.environ[db_var]
        conn = connect(database)
        try:
            conn.cursor().execute(ENSURE_USER, (user, os.environ[pw_var]))
            conn.commit()
        finally:
            conn.close()
        print(f"{database}: user {user} ready (db_owner)")


if __name__ == "__main__":
    main()

# devops-teamManagement

An internal tool for a yacht brokerage. It tracks each team member's quarterly KPI targets against what they actually achieved. It also scores incoming leads, assigns each one to a broker automatically, and ranks brokers by how their leads turn out.

It runs as two Flask JSON services, each with its own SQL Server database, plus a static front end, all behind one nginx proxy:

| Part | Folder | Owns |
| --- | --- | --- |
| KPI service | `services/kpi` | roles, members, KPI definitions, quarterly targets, the dashboard |
| Routing service | `services/routing` | leads, outcomes, broker scoring, assignment, the leaderboard |
| Front end | `ui` | plain HTML/CSS/JS, no build step |
| Proxy | `deploy/nginx.conf` | `/` → ui, `/api/kpi/` → kpi, `/api/routing/` → routing, `/health`, `/lb-probe` |
| Infrastructure | `infra/terraform` | Azure VM, load balancer, DNS zone, SQL server and databases |

The services call each other over HTTP with a timeout, and each keeps working when the other is down:

- **Dashboard** (KPI → routing `/activity`): if routing is down, targets are shown without actuals, with a notice.
- **New lead** (routing → KPI `/brokers/active`): if KPI is down, the lead is saved unassigned, with a notice.
- **Leaderboard** (routing → KPI): if KPI is down, it ranks every member who has leads.

## Run it locally

Requires Docker Desktop. On Apple Silicon, enable "Use Rosetta for x86_64/amd64 emulation" in Docker Desktop's settings, because SQL Server only ships for amd64.

```
docker compose up --build
```

Then open http://localhost:8080. The first start pulls SQL Server, creates the `kpi` and `routing` databases and their logins (`db/init.sql`), runs each service's migrations, and loads demo data: 4 roles, 6 members, targets for the current quarter, and 30 leads.

| URL | What |
| --- | --- |
| http://localhost:8080 | the app, through the proxy |
| http://localhost:8080/health | 200 only when both services and their databases are healthy |
| http://localhost:8001/health, http://localhost:8002/health | each service directly, for debugging |

The passwords in `docker-compose.yml` are local-only defaults. Override them with a `.env` file (git-ignored).

To try the failure modes: `docker compose stop kpi` or `docker compose stop routing`, use the app, then `docker compose start kpi` (or `routing`).

To start again with an empty database: `docker compose down -v`.

After editing `deploy/nginx.conf`, run `docker compose up -d --force-recreate proxy`. A plain `nginx -s reload` can read a stale copy of the file, because Docker Desktop bind-mounts a single file by inode and editors replace the file.

## Service configuration

Both services read these environment variables:

| Variable | Example | What it does |
| --- | --- | --- |
| `DATABASE_URL` | `mssql://kpi_svc:...@sqlserver:1433/kpi` | The service's own database. Required. |
| `PORT` | `8000` | Port gunicorn listens on. |
| `SEED_DEMO` | `1` | Loads demo data on start, only if the database is still empty. |
| `CORS_ORIGINS` | `http://localhost:8080` | Origins allowed to call the API directly (not needed through the proxy). |
| `GIT_SHA` | `local` | Reported by `/health` as the running version. |
| `DB_CONNECT_RETRIES` | `8` | Connection attempts, so a paused Azure SQL database has time to resume. |
| `ROUTING_URL`, `ROUTING_TIMEOUT_S` | `http://routing:8000`, `2` | KPI service only: where routing is, and how long to wait for it. |
| `KPI_URL`, `KPI_TIMEOUT_S` | `http://kpi:8000`, `2` | Routing service only: where KPI is, and how long to wait for it. |

## Database migrations

Each service runs its own numbered SQL files from `migrations/` on start (`migrate.py`). Applied files are recorded in a `schema_migrations` table, so a second start applies nothing. Every schema change after `001` is a new numbered file; an applied file is never edited.

## Run a single service

`docker compose up --build kpi` starts only SQL Server, the database setup and the KPI
service, at http://localhost:8001 (routing: `docker compose up --build routing`, port 8002;
it also starts kpi, which it needs only for the demo seed). Without the other service, the
cross-service features degrade as described above.

Or without Docker for the service itself (Python 3.12), with the database from compose:

```
docker compose up -d sqlserver db-init
cd services/kpi
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
DATABASE_URL=mssql://kpi_svc:Local_Kpi_Passw0rd@localhost:1433/kpi ROUTING_URL=http://localhost:8002 SEED_DEMO=1 python app.py
```

## Tests

Each service has its own tests in `services/<name>/tests/`:

| File | What it covers |
| --- | --- |
| `test_service.py` | the business logic, against a real SQL Server database (ported from Assignment 1) |
| `test_migrate.py` | the migration runner: runs once, a second run applies nothing, a failed migration is rolled back, a later migration keeps existing rows |
| `test_api.py` | every HTTP route through Flask's test client, including `/health`, the request log line, and both failure paths of the seam with the other service stubbed by `responses` |
| `test_routing_client.py` / `test_kpi_client.py` | the outbound call: success, timeout, connection error, error status |

The database tests need a SQL Server login that may create databases. They create a fresh
database with a random name, run the real migrations into it, and drop it at the end. Without
`DATABASE_URL` they are skipped and only the pure unit tests run.

```
docker run -d --name sqltest -e ACCEPT_EULA=Y -e MSSQL_SA_PASSWORD='Test_Sa_Passw0rd' -p 11433:1433 \
  mcr.microsoft.com/mssql/server:2022-latest

cd services/kpi            # or services/routing
pip install -r requirements.txt -r requirements-dev.txt
DATABASE_URL='mssql://sa:Test_Sa_Passw0rd@localhost:11433/master' pytest --cov --cov-report=term-missing
ruff check . && ruff format --check .
```

`--cov` measures `service.py` and `migrate.py`, the core logic (`[tool.coverage.run]` in
`pyproject.toml`). CI fails under 70%. Current result: **kpi 100% (91 tests), routing 100% (93 tests)**.

### Cross-service integration test

`tests/integration/test_seam.py` runs against the real compose stack, through the proxy. Nothing
is stubbed: KPI's dashboard really calls routing, and routing's new-lead flow really calls KPI.

```
docker compose up -d --build
pip install -r tests/integration/requirements.txt
STACK_URL=http://localhost:8080 pytest tests/integration

docker compose stop routing
SEAM_ROUTING_STOPPED=1 STACK_URL=http://localhost:8080 pytest tests/integration
docker compose start routing

docker compose stop kpi
SEAM_KPI_STOPPED=1 STACK_URL=http://localhost:8080 pytest tests/integration
docker compose start kpi
```

## CI/CD

`.github/workflows/ci.yml` runs on every push and pull request, and never touches Azure:

- per service: ruff, pytest against a SQL Server service container with coverage (fails under 70%), and `docker build`
- the integration test above, on the compose stack, with each service stopped in turn, plus a check that a restart applies no migrations
- `terraform fmt -check` and `terraform validate`
- `openapi-spec-validator` on both OpenAPI documents, `check-jsonschema` on `system.yaml`, and actionlint on the workflows

`.github/workflows/cd.yml` runs only after CI succeeded for a push to `main`:

1. builds both images and pushes them to GHCR, tagged with the commit SHA
2. `terraform plan` and `apply` in `infra/terraform/`: VM, load balancer, public IP, DNS zone, SQL server and databases (remote state in Azure storage)
3. creates or updates each service's contained database user (`deploy/create_db_users.py`)
4. ships `deploy/docker-compose.prod.yml`, `deploy/nginx.conf`, `ui/` and a `.env` built from secrets to the VM, and runs `docker compose pull && up -d` there (`az vm run-command`)
5. polls `/health` for up to 3 minutes, and fails unless it returns 200 with the new SHA

## Deployment

Live URL: http://jelaawar-ieu2023.westeurope.cloudapp.azure.com (TODO: confirm after the first deploy)

The one-time setup (Terraform state storage, service principal role, SSH key, secrets) is in
[infra/bootstrap.md](infra/bootstrap.md). After that, every merge to `main` deploys.

### GitHub secrets (names only)

| Secret | Used for |
| --- | --- |
| `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` | the class service principal: Terraform and `az` |
| `TF_STATE_RESOURCE_GROUP`, `TF_STATE_STORAGE_ACCOUNT`, `TF_STATE_CONTAINER` | where the Terraform state lives |
| `SQL_ADMIN_PASSWORD` | SQL server admin; used only by Terraform and to create the service users |
| `KPI_DB_PASSWORD`, `ROUTING_DB_PASSWORD` | each service's own database user |
| `ADMIN_CIDR` | the only source address allowed to SSH in |

`GITHUB_TOKEN` is provided by GitHub: it pushes the images and lets the VM pull them during a deploy.

### GitHub variables (names only)

| Variable | Used for |
| --- | --- |
| `AZURE_RESOURCE_GROUP` | the class resource group everything goes into |
| `VM_SSH_PUBLIC_KEY` | public key for SSH to the VM |
| `SEED_DEMO` | optional, default `1`: demo data while the databases are empty |

### Leaked secrets

None so far. If a secret is ever pushed: rotate it within 24 hours (or report it to the
professor for the class service principal), update the GitHub secret, remove it from the code,
and record here what leaked, when, and what was done.

## Branching workflow

Work is done on feature branches. Each branch is merged into `main` through a pull request.

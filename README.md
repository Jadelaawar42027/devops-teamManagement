# devops-teamManagement

An internal tool for a yacht brokerage. It tracks each team member's quarterly KPI targets against what they actually achieved. It also scores incoming leads, assigns each one to a broker automatically, and ranks brokers by how their leads turn out.

**Live URL:** https://TODO-after-first-deploy.azurestaticapps.net (the Static Web App `jelaawar-ieu2023-ui`; TODO: fill in after the first deploy)

Assignment 1 built it as one Flask + SQLite app. Assignment 2 splits it into two services with their own databases, runs it with Docker Compose, and deploys it to Azure (Container Apps, Azure SQL serverless, Static Web Apps) with Terraform and GitHub Actions. The design decisions are in [ADR.md](ADR.md), and AI use is logged in [AI_USAGE.md](AI_USAGE.md).

## Architecture

| Part | Folder | Owns |
| --- | --- | --- |
| KPI service | `services/kpi` | roles, members, KPI definitions, quarterly targets, the dashboard |
| Routing service | `services/routing` | leads, outcomes, broker scoring, assignment, the leaderboard |
| Front end | `ui` | static HTML/CSS/JS, no build step |
| Infrastructure | `infra/terraform` | the Azure resources (see "Initial Azure setup") |

```mermaid
flowchart LR
  B[Browser] -->|HTTPS| UI[Static Web App<br/>jelaawar-ieu2023-ui]
  B -->|HTTPS + CORS| K[Container App<br/>jelaawar-ieu2023-kpi]
  B -->|HTTPS + CORS| R[Container App<br/>jelaawar-ieu2023-routing]
  K -->|GET /activity, 2 s timeout| R
  R -->|GET /brokers/active, 2 s timeout| K
  K --> KD[(jelaawar-ieu2023-kpi-db<br/>Azure SQL serverless)]
  R --> RD[(jelaawar-ieu2023-routing-db<br/>Azure SQL serverless)]
```

Each service is a Flask JSON API (Python 3.12, gunicorn, raw SQL with pymssql) in its own container, with its own SQL Server database and its own database user, which cannot open the other database. The browser loads the static UI, then calls both services directly. Their URLs are in `ui/config.js`, which the pipeline generates for Azure. Each service accepts browser calls only from the UI's origin (`CORS_ORIGINS`).

The services call each other over HTTP with a timeout, and each keeps working when the other is down:

- **Dashboard** (KPI → routing `/activity`): if routing is down, targets are shown without actuals, with a notice.
- **New lead** (routing → KPI `/brokers/active`): if KPI is down, the lead is saved unassigned, with a notice.
- **Leaderboard** (routing → KPI): if KPI is down, it ranks every member who has leads, with a notice.

Every endpoint is described in `services/kpi/openapi.yaml` and `services/routing/openapi.yaml`. The whole system, including every environment variable, is described in `system.yaml`.

## Run it locally

Requires Docker Desktop. On Apple Silicon, enable "Use Rosetta for x86_64/amd64 emulation" in Docker Desktop's settings, because SQL Server only ships for amd64.

```
docker compose up --build
```

Then open http://localhost:8080. The first start does four things:

1. pulls SQL Server;
2. creates the `kpi` and `routing` databases and their logins (`db/init.sql`, run by the one-off `db-init` service);
3. runs each service's migrations;
4. loads demo data: 4 roles, 6 members, targets for the current quarter, and 30 leads.

| URL | What |
| --- | --- |
| http://localhost:8080 | the UI (stock nginx serving `ui/`) |
| http://localhost:8001/health | the KPI service |
| http://localhost:8002/health | the routing service |

The passwords in `docker-compose.yml` are local-only defaults. Override them with a `.env` file (git-ignored).

- **Try the failure modes:** `docker compose stop kpi` or `docker compose stop routing`, use the app, then `docker compose start kpi` (or `routing`).
- **Start again with an empty database:** `docker compose down -v`.

### Service configuration

Both services read these environment variables (with defaults, also in `system.yaml`):

| Variable | Default | What it does |
| --- | --- | --- |
| `DATABASE_URL` | none (secret) | The service's own database, `mssql://user:password@host:1433/database`. Required. |
| `PORT` | `8000` | Port gunicorn listens on. |
| `SEED_DEMO` | empty | `1` loads demo data on start, only if the database is still empty. |
| `CORS_ORIGINS` | empty | Origins allowed to call the API from a browser: the UI's origin. |
| `GIT_SHA` | `dev` | Reported by `/health` as the running version. |
| `DB_CONNECT_RETRIES` | `8` | Connection attempts with backoff, so a paused Azure SQL database has time to resume. |
| `ROUTING_URL`, `ROUTING_TIMEOUT_S` | `http://routing:8000`, `2` | KPI service only: where routing is, and how long to wait for it. |
| `KPI_URL`, `KPI_TIMEOUT_S` | `http://kpi:8000`, `2` | Routing service only: where KPI is, and how long to wait for it. |

### Database migrations

Each service runs its own numbered SQL files from `migrations/` on start (`migrate.py`). Applied files are recorded in a `schema_migrations` table, so a second start applies nothing. Each file runs in one transaction, so a failed migration leaves nothing half-applied. Every schema change after `001` is a new numbered file, and an applied file is never edited. `later/` holds migration 002 and its code changes, to be applied once Azure holds data (`later/README.txt`).

## Run one service alone

`docker compose up --build kpi` starts only SQL Server, the database setup and the KPI service, at http://localhost:8001. For routing, use `docker compose up --build routing` (port 8002). It also starts kpi, but only so the demo seed can find brokers. Without the other service, the cross-service features degrade as described above.

Or run the service without Docker (Python 3.12), using the database from compose:

```
docker compose up -d sqlserver db-init
cd services/kpi
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
DATABASE_URL=mssql://kpi_svc:Local_Kpi_Passw0rd@localhost:1433/kpi ROUTING_URL=http://localhost:8002 SEED_DEMO=1 python app.py
```

## Run the tests

Each service has its own tests in `services/<name>/tests/`:

| File | What it covers |
| --- | --- |
| `test_service.py` | the business logic, against a real SQL Server database (ported from Assignment 1) |
| `test_migrate.py` | the migration runner: runs once, a second run applies nothing, a failed migration is rolled back, a later migration keeps existing rows |
| `test_api.py` | every HTTP route through Flask's test client, including `/health`, the request log line, CORS, and both failure paths of the seam with the other service stubbed by `responses` |
| `test_routing_client.py` / `test_kpi_client.py` | the outbound call: success, timeout, connection error, error status |

The database tests need a SQL Server login that may create databases. They create a fresh database with a random name, run the real migrations into it, and drop it at the end. Without `DATABASE_URL` they are skipped and only the pure unit tests run.

```
docker run -d --name sqltest -e ACCEPT_EULA=Y -e MSSQL_SA_PASSWORD='Test_Sa_Passw0rd' -p 11433:1433 \
  mcr.microsoft.com/mssql/server:2022-latest

cd services/kpi            # or services/routing
pip install -r requirements.txt -r requirements-dev.txt
DATABASE_URL='mssql://sa:Test_Sa_Passw0rd@localhost:11433/master' pytest --cov --cov-report=term-missing
ruff check . && ruff format --check .
```

`--cov` measures `service.py` and `migrate.py`, the core logic (`[tool.coverage.run]` in `pyproject.toml`). CI fails under 70%. Current result: **kpi 100% (91 tests), routing 100% (93 tests)**.

### Cross-service integration test

`tests/integration/test_seam.py` runs against the real compose stack. Nothing is stubbed: KPI's dashboard really calls routing, and routing's new-lead flow really calls KPI.

```
docker compose up -d --build
pip install -r tests/integration/requirements.txt
export KPI_URL=http://localhost:8001 ROUTING_URL=http://localhost:8002
pytest tests/integration

docker compose stop routing && SEAM_ROUTING_STOPPED=1 pytest tests/integration && docker compose start routing
docker compose stop kpi && SEAM_KPI_STOPPED=1 pytest tests/integration && docker compose start kpi
```

## Initial Azure setup (one time)

Everything in Azure is created by Terraform (`infra/terraform/`) from the CD pipeline, in the class's shared resource group. Before the first deploy:

1. **Get from the professor:**
   - the class resource group name (`rg-sdd-3a` or `rg-sdd-3b`);
   - the class service principal (Contributor on that resource group);
   - a storage account and container for Terraform's state. TODO: ask the professor; I create no extra resources.
2. **Check the resource providers are registered** (the service principal cannot register them). Run `az login`, then:
   ```
   for p in Microsoft.App Microsoft.Sql Microsoft.Web; do echo "$p $(az provider show -n $p --query registrationState -o tsv)"; done
   ```
3. **Set the GitHub secrets and variables** listed below, from the repository folder. `gh secret set NAME` prompts for the value, so it is never in a file or in your shell history. For the three database passwords, use generated values: `gh secret set KPI_DB_PASSWORD --body "$(openssl rand -base64 24 | tr -d '/+=')Aa1-"`.
4. **Merge a pull request into `main`.** CD runs. On this first run, the `ui` job stops: the Static Web App's deployment token only exists once Terraform has created the app. Get the token:
   ```
   az staticwebapp secrets list -g <resource group> -n jelaawar-ieu2023-ui --query properties.apiKey -o tsv
   ```
   then run `gh secret set AZURE_STATIC_WEB_APPS_API_TOKEN` and "Re-run failed jobs".
5. **Make the images pullable.** GHCR packages start private, and a Container App pulls its image every time it starts from zero. After the first run has pushed them, go to github.com → Packages → `kpi` and `routing` → Package settings → Change visibility → Public. The images hold no secrets. Then re-run the failed jobs.
6. **Record the URL.** Copy the `ui_url` from the run's log into `system.yaml` (`public_url`) and into this README.

The service principal needs only **Contributor on the class resource group**. That lets it create the resources below, read the state storage keys, read the Static Web App's settings, and add or remove a temporary SQL firewall rule for the pipeline runner. It never creates a resource group and needs no role assignments.

Terraform creates exactly these resources (assignment §7):

| Resource | Name | Billing |
| --- | --- | --- |
| Azure SQL logical server | `jelaawar-ieu2023-sql` | free in itself |
| Azure SQL database, serverless (GP_S_Gen5_1: 0.5-1 vCore, auto-pause after 15 min, 2 GB, local backups) | `jelaawar-ieu2023-kpi-db` | pay-per-use |
| Azure SQL database, same settings | `jelaawar-ieu2023-routing-db` | pay-per-use |
| SQL firewall rule "allow Azure services" | `AllowAzureServices` | free (a setting) |
| Container Apps environment, Consumption, no Log Analytics | `jelaawar-ieu2023-env` | no cost of its own |
| Container App (0-1 replicas, HTTPS ingress) | `jelaawar-ieu2023-kpi` | pay-per-use |
| Container App (0-1 replicas, HTTPS ingress) | `jelaawar-ieu2023-routing` | pay-per-use |
| Static Web App, Free tier | `jelaawar-ieu2023-ui` | free |

To run Terraform by hand (rarely needed):

```
cd infra/terraform
export ARM_SUBSCRIPTION_ID=$(az account show --query id -o tsv)
export TF_VAR_resource_group_name=... TF_VAR_image_tag=<a SHA in GHCR>
export TF_VAR_sql_admin_password=... TF_VAR_kpi_db_password=... TF_VAR_routing_db_password=...
terraform init -backend-config="resource_group_name=..." -backend-config="storage_account_name=..." \
  -backend-config="container_name=..." -backend-config="key=jelaawar-ieu2023.tfstate"
terraform plan
```

## Deployment

`.github/workflows/ci.yml` runs on every push and pull request, and never touches Azure:

- per service: ruff, pytest against a SQL Server service container with coverage (fails under 70%), and `docker build`
- the integration test above, on the compose stack, with each service stopped in turn, plus a check that a restart applies no migrations
- `terraform fmt -check` and `terraform validate`
- `openapi-spec-validator` on both OpenAPI documents, `check-jsonschema` on `system.yaml`, and actionlint on the workflows

`.github/workflows/cd.yml` runs only after CI succeeded for a push to `main`, so changes reach Azure by merging a pull request:

1. builds both images and pushes them to GHCR, tagged with the commit SHA
2. `terraform apply` for the SQL server and databases
3. creates or updates each service's own database user (`infra/scripts/create_db_users.py`), through a temporary firewall rule for the runner
4. `terraform plan` and `apply` for everything else, which updates both Container Apps to the new image tag
5. generates `ui/config.js` with the two Container Apps' URLs, and deploys `ui/` to the Static Web App with its deployment token
6. polls both services' `/health` for up to 3 minutes, and fails unless they return 200 with the new SHA

Live logs: `az containerapp logs show -g <resource group> -n jelaawar-ieu2023-routing --type console --follow`.

### GitHub secrets and variables (names only)

| Secret | Used for |
| --- | --- |
| `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` | the class service principal: Terraform and `az` |
| `TF_STATE_RESOURCE_GROUP`, `TF_STATE_STORAGE_ACCOUNT`, `TF_STATE_CONTAINER` | where the Terraform state lives |
| `SQL_ADMIN_PASSWORD` | SQL server admin; used only by Terraform and to create the service users |
| `KPI_DB_PASSWORD`, `ROUTING_DB_PASSWORD` | each service's own database user; passed to the Container Apps as secrets |
| `AZURE_STATIC_WEB_APPS_API_TOKEN` | the Static Web App's deployment token |
| `GHCR_PULL_USER`, `GHCR_PULL_TOKEN` | optional: only if the GHCR packages stay private |

| Variable | Used for |
| --- | --- |
| `AZURE_RESOURCE_GROUP` | the class resource group |
| `SEED_DEMO` | optional, default `1`: demo data while the databases are empty |

`GITHUB_TOKEN` is provided by GitHub and pushes the images.

### Leaked secrets

None so far. If a secret is ever pushed: rotate it within 24 hours (or report it to the professor, for the class service principal), update the GitHub secret, remove it from the code, and record here what leaked, when, and what was done.

## Branching workflow

Work is done on feature branches. Each branch is merged into `main` through a pull request, so CI runs before CD.

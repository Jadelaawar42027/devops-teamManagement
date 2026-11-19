# devops-teamManagement

An internal tool for a yacht brokerage. It tracks each team member's quarterly KPI targets against what they actually achieved. It also scores incoming leads, assigns each one to a broker automatically, and ranks brokers by how their leads turn out.

**Live URL:** http://jelaawar-ieu2023.westeurope.cloudapp.azure.com (TODO: confirm after the first deploy)

Assignment 1 built it as one Flask + SQLite app. Assignment 2 splits it into two services with their own databases, runs it with Docker Compose, and deploys it to Azure with Terraform and GitHub Actions. The design decisions are in [ADR.md](ADR.md), and AI use is logged in [AI_USAGE.md](AI_USAGE.md).

## Architecture

| Part | Folder | Owns |
| --- | --- | --- |
| KPI service | `services/kpi` | roles, members, KPI definitions, quarterly targets, the dashboard |
| Routing service | `services/routing` | leads, outcomes, broker scoring, assignment, the leaderboard |
| Front end | `ui` | plain HTML/CSS/JS, no build step |
| Proxy | `deploy/nginx.conf` | `/` → ui, `/api/kpi/` → kpi, `/api/routing/` → routing, `/health`, `/lb-probe` |
| Infrastructure | `infra/terraform` | Azure VM, load balancer, DNS zone, SQL server and databases |

```mermaid
flowchart LR
  B[Browser] -->|HTTP :80| P[nginx proxy]
  P -->|/| UI[ui: static files]
  P -->|/api/kpi/| K[KPI service]
  P -->|/api/routing/| R[Routing service]
  K -->|GET /activity, 2 s timeout| R
  R -->|GET /brokers/active, 2 s timeout| K
  K --> KD[(kpi database)]
  R --> RD[(routing database)]
```

Each service is a Flask JSON API (Python 3.12, gunicorn, raw SQL with pymssql) with its own SQL Server database and its own database user, which cannot open the other database. They call each other over HTTP with a timeout, and each keeps working when the other is down:

- **Dashboard** (KPI → routing `/activity`): if routing is down, targets are shown without actuals, with a notice.
- **New lead** (routing → KPI `/brokers/active`): if KPI is down, the lead is saved unassigned, with a notice.
- **Leaderboard** (routing → KPI): if KPI is down, it ranks every member who has leads.

Every endpoint is described in `services/kpi/openapi.yaml` and `services/routing/openapi.yaml`. The whole system, including every environment variable, is described in `system.yaml`.

On Azure the same four containers run on one VM, behind a load balancer with a public DNS name. The databases are two Azure SQL serverless databases (ADR-8):

```mermaid
flowchart LR
  U[Internet] --> LB[Load balancer + public IP<br/>jelaawar-ieu2023.westeurope.cloudapp.azure.com]
  DNS[Azure DNS zone<br/>app.jelaawar-ieu2023.devops.ie] -.A record.-> LB
  LB -->|:80| VM[VM: docker compose<br/>proxy, ui, kpi, routing]
  VM --> SQL[(Azure SQL serverless<br/>kpi-db, routing-db)]
```

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

- **Try the failure modes:** `docker compose stop kpi` or `docker compose stop routing`, use the app, then `docker compose start kpi` (or `routing`).
- **Start again with an empty database:** `docker compose down -v`.
- **After editing `deploy/nginx.conf`:** run `docker compose up -d --force-recreate proxy`. A plain `nginx -s reload` can read a stale copy of the file, because Docker Desktop bind-mounts a single file by inode and editors replace the file.

### Service configuration

Both services read these environment variables (the full list with defaults is in `system.yaml`):

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

### Database migrations

Each service runs its own numbered SQL files from `migrations/` on start (`migrate.py`). Applied files are recorded in a `schema_migrations` table, so a second start applies nothing. Each file runs in one transaction, so a failed migration leaves nothing half-applied. Every schema change after `001` is a new numbered file; an applied file is never edited. `later/` holds migration 002 and its code changes, to be applied once Azure holds data (see `later/README.txt`).

## Run one service alone

`docker compose up --build kpi` starts only SQL Server, the database setup and the KPI service, at http://localhost:8001. For routing, use `docker compose up --build routing` (port 8002); it also starts kpi, which it needs only for the demo seed. Without the other service, the cross-service features degrade as described above.

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
| `test_api.py` | every HTTP route through Flask's test client, including `/health`, the request log line, and both failure paths of the seam with the other service stubbed by `responses` |
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

`tests/integration/test_seam.py` runs against the real compose stack, through the proxy. Nothing is stubbed: KPI's dashboard really calls routing, and routing's new-lead flow really calls KPI.

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

## Terraform setup

All Azure resources are defined in `infra/terraform/`:

| File | Defines |
| --- | --- |
| `network.tf` | the resource group (read, or created), virtual network, subnet and NSG: port 80 open, SSH only from `admin_cidr` |
| `vm.tf` + `cloud-init.yaml` | the Ubuntu 24.04 VM, with no public IP. cloud-init installs Docker and creates `/opt/app` |
| `lb.tf` | the Standard load balancer and static public IP (DNS label `jelaawar-ieu2023`): rule 80→80, probe `/lb-probe`, NAT 50022→22, outbound rule |
| `dns.tf` | the DNS zone `jelaawar-ieu2023.devops.ie` and the A record `app` |
| `sql.tf` | the SQL server, two serverless databases (GP_S_Gen5_1, 0.5 vCore minimum, auto-pause 15 min, 2 GB, local backups) and the firewall rules |
| `variables.tf`, `outputs.tf`, `providers.tf` | inputs, outputs, the azurerm provider and the empty `azurerm` backend |

Terraform needs two things that exist before it runs: a storage account for its state, and the service principal. Their one-time setup (`az` commands, the role the service principal needs, the SSH key and the GitHub secrets) is in **[infra/bootstrap.md](infra/bootstrap.md)**. The pipeline then runs `terraform init` (with the backend passed as `-backend-config`), `plan` and `apply` on every deploy. To run it by hand, see the end of `infra/bootstrap.md`. Never commit a `terraform.tfvars` or a state file: both are git-ignored.

## Deploy

`.github/workflows/ci.yml` runs on every push and pull request, and never touches Azure:

- per service: ruff, pytest against a SQL Server service container with coverage (fails under 70%), and `docker build`
- the integration test above, on the compose stack, with each service stopped in turn, plus a check that a restart applies no migrations
- `terraform fmt -check` and `terraform validate`
- `openapi-spec-validator` on both OpenAPI documents, `check-jsonschema` on `system.yaml`, and actionlint on the workflows

`.github/workflows/cd.yml` runs only after CI succeeded for a push to `main`, so changes reach production by merging a pull request. Nothing is deployed by hand:

1. builds both images and pushes them to GHCR, tagged with the commit SHA
2. `terraform plan` and `apply`: VM, load balancer, public IP, DNS zone, SQL server and databases (remote state in Azure storage)
3. creates or updates each service's contained database user (`deploy/create_db_users.py`), through a temporary firewall rule for the runner
4. ships `deploy/docker-compose.prod.yml`, `deploy/nginx.conf`, `ui/` and a `.env` built from secrets to the VM, and runs `docker compose pull && up -d` there (`az vm run-command`)
5. polls `/health` for up to 3 minutes, and fails unless it returns 200 with the new SHA

To look at the running system: `ssh -i ~/.ssh/jelaawar-azure -p 50022 azureuser@jelaawar-ieu2023.westeurope.cloudapp.azure.com` (only from `ADMIN_CIDR`), then `sudo docker compose -f /opt/app/deploy/docker-compose.prod.yml logs`.

### GitHub secrets (names only)

| Secret | Used for |
| --- | --- |
| `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID` | the class service principal: Terraform and `az` |
| `TF_STATE_RESOURCE_GROUP`, `TF_STATE_STORAGE_ACCOUNT`, `TF_STATE_CONTAINER` | where the Terraform state lives |
| `SQL_ADMIN_PASSWORD` | SQL server admin; used only by Terraform and to create the service users |
| `KPI_DB_PASSWORD`, `ROUTING_DB_PASSWORD` | each service's own database user |
| `ADMIN_CIDR` | the only source address allowed to SSH in |

`GITHUB_TOKEN` is provided by GitHub: it pushes the images, and lets the VM pull them during a deploy.

### GitHub variables (names only)

| Variable | Used for |
| --- | --- |
| `AZURE_RESOURCE_GROUP` | the class resource group everything goes into |
| `VM_SSH_PUBLIC_KEY` | public key for SSH to the VM |
| `SEED_DEMO` | optional, default `1`: demo data while the databases are empty |

### Leaked secrets

None so far. If a secret is ever pushed: rotate it within 24 hours (or report it to the professor, for the class service principal), update the GitHub secret, remove it from the code, and record here what leaked, when, and what was done.

## Live URL and DNS proof

- App: http://jelaawar-ieu2023.westeurope.cloudapp.azure.com
- Health: http://jelaawar-ieu2023.westeurope.cloudapp.azure.com/health

The Azure DNS zone `jelaawar-ieu2023.devops.ie` is real but not delegated, because I own no domain, so public resolvers do not know it. Ask one of its own Azure name servers directly:

```
NS=$(az network dns zone show -g <resource-group> -n jelaawar-ieu2023.devops.ie --query "nameServers[0]" -o tsv)
nslookup app.jelaawar-ieu2023.devops.ie "$NS"
```

The answer is the load balancer's public IP: the same address `jelaawar-ieu2023.westeurope.cloudapp.azure.com` resolves to. Every CD run checks this in its last step.

## Branching workflow

Work is done on feature branches. Each branch is merged into `main` through a pull request, so CI runs before CD.

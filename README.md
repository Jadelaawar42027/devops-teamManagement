# devops-teamManagement

An internal tool for a yacht brokerage. It tracks each team member's quarterly KPI targets against what they actually achieved. It also scores incoming leads, assigns each one to a broker automatically, and ranks brokers by how their leads turn out.

It runs as two Flask JSON services, each with its own SQL Server database, plus a static front end, all behind one nginx proxy:

| Part | Folder | Owns |
| --- | --- | --- |
| KPI service | `services/kpi` | roles, members, KPI definitions, quarterly targets, the dashboard |
| Routing service | `services/routing` | leads, outcomes, broker scoring, assignment, the leaderboard |
| Front end | `ui` | plain HTML/CSS/JS, no build step |
| Proxy | `deploy/nginx.conf` | `/` → ui, `/api/kpi/` → kpi, `/api/routing/` → routing, `/health` |

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

## Tests

Run from a service folder, for example `services/kpi`:

```
pip install -r requirements.txt -r requirements-dev.txt
pytest
ruff check . && ruff format --check .
```

## Branching workflow

Work is done on feature branches. Each branch is merged into `main` through a pull request.

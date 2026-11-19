# Split, ship and operate: the brokerage KPI and lead-routing tool

**Student:** Jad El Aawar (jelaawar.ieu2023) · **Course:** Software Development & DevOps, Assignment 2
**Repository:** https://github.com/Jadelaawar42027/devops-teamManagement · **Graded commit:** `submission` tag, SHA [EVIDENCE: full SHA of the tagged commit]
**Live URL:** https://TODO.azurestaticapps.net, the Static Web App `jelaawar-ieu2023-ui` [EVIDENCE: replace with the exact `ui_url` and confirm it answers after the final deploy]

> Draft. Every `[EVIDENCE: ...]` marks a screenshot, link or log I still have to take. Replace each one and delete this note before exporting to PDF (4-5 pages).

## 1. What changed, in one paragraph

Assignment 1 was one Flask app with two packages, `kpi` and `routing`, sharing one SQLite file and rendering Jinja pages. Assignment 2 splits it along the seam I drew in ADR-2 into two services, each with its own container, its own SQL Server database and its own database user. A static front end replaces the templates. Everything runs locally with `docker compose up --build`. On Azure it runs on pay-per-use infrastructure created entirely by Terraform from the CD pipeline: two Container Apps that scale to zero, two serverless SQL databases, and a Static Web App for the UI (ADR-8). Every push is tested, and every merge to `main` is deployed with no manual step.

## 2. Architecture before and after

**Before (Assignment 1): one process, one database file.** The only links between the domains were two in-process function calls, which the split turned into HTTP.

```mermaid
flowchart TB
  subgraph Monolith["Flask app (one process)"]
    direction LR
    KR[kpi/routes.py<br/>Jinja pages] --> KS[kpi/service.py]
    RR[routing/routes.py<br/>Jinja pages] --> RS[routing/service.py]
    KS -- "activity_counts()<br/>in-process call" --> RS
    RR -- "active_broker_ids()<br/>in-process call" --> KS
  end
  KS --> DB[(app.db: SQLite<br/>roles, members, kpi_definitions, kpi_targets,<br/>leads, lead_outcomes)]
  RS --> DB
  U[Browser] -->|HTML forms| Monolith
```

**After (Assignment 2): two services, two databases, HTTP across the seam.** The browser loads the static UI, then calls each service directly. Locally that is ports 8001 and 8002; on Azure, each Container App's HTTPS URL. Each service accepts the UI's origin only (CORS).

```mermaid
flowchart LR
  U[Browser] -->|loads| UI[ui: static HTML/CSS/JS<br/>nginx locally, Static Web App on Azure]
  U -->|"HTTP(S) + CORS"| K[KPI service<br/>Flask + gunicorn]
  U -->|"HTTP(S) + CORS"| R[Routing service<br/>Flask + gunicorn]
  K -- "GET /activity?quarter=&member_ids=<br/>timeout 2 s" --> R
  R -- "GET /brokers/active<br/>timeout 2 s" --> K
  K --> KD[(kpi database<br/>user kpi_svc)]
  R --> RD[(routing database<br/>user routing_svc)]
```

The seam held (ADR-6). Exactly two endpoints cross it, both called server side:

- **Dashboard** (KPI `GET /dashboard`): KPI reads targets from its own database, then makes one bulk call to routing's `/activity` for the actuals. If routing does not answer within 2 s, the dashboard still answers 200, with every target shown, `actual` and `percent` set to null, and a notice.
- **New lead** (routing `POST /leads`): routing saves the lead, then asks KPI's `/brokers/active` who can take it. If KPI is down, the lead stays saved without a broker and the response says so. The leaderboard falls back to every member who has leads.

What changed from ADR-2: the per-member `activity_counts()` became a bulk endpoint, so a down routing service costs the dashboard one 2-second timeout instead of one per member. Member names are joined in the browser from KPI's `/members`, and shown as `#id` when KPI is down. The cross-domain foreign key that never existed (ADR-3) is enforced in code: routing only assigns ids it just got from KPI, and KPI only deactivates members, never deletes them (ADR-7).

## 3. Deployment

```mermaid
flowchart LR
  subgraph GitHub
    PR[Pull request] --> CI["CI workflow<br/>lint · tests + coverage · images<br/>compose integration · terraform validate · specs"]
    CI -- "success on main<br/>(workflow_run)" --> CD[CD workflow]
  end
  CD -- "push :SHA" --> GHCR[(GHCR<br/>ghcr.io/jadelaawar42027/kpi<br/>ghcr.io/jadelaawar42027/routing)]
  CD -- "terraform plan + apply" --> TF[(Terraform state<br/>storage provided by the professor)]
  CD -- "config.js + deploy ui/<br/>(deployment token)" --> WEB
  CD -- "poll /health ≤ 3 min" --> K
  subgraph Azure["Azure: resource group rg-sdd-3a"]
    WEB[Static Web App, Free<br/>jelaawar-ieu2023-ui]
    subgraph ENV["Container Apps environment jelaawar-ieu2023-env (Consumption)"]
      K[jelaawar-ieu2023-kpi<br/>0-1 replicas, HTTPS]
      R[jelaawar-ieu2023-routing<br/>0-1 replicas, HTTPS]
    end
    SQL[SQL server jelaawar-ieu2023-sql]
    SQL --- D1[(jelaawar-ieu2023-kpi-db<br/>serverless)]
    SQL --- D2[(jelaawar-ieu2023-routing-db<br/>serverless)]
    K --> D1
    R --> D2
    K <-->|HTTPS, 2 s timeout| R
  end
  GHCR -. "image pull at start" .-> ENV
  U[Browser] -->|HTTPS| WEB
  U -->|HTTPS + CORS| K
  U -->|HTTPS + CORS| R
```

Terraform in `infra/terraform/` creates 8 resources in the class resource group (read through a data source, never created), and nothing else:

- the SQL server, its two GP_S_Gen5_1 databases (0.5 to 1 vCore, auto-pause after 15 minutes, 2 GB, locally redundant backups) and an "allow Azure services" firewall rule;
- the Container Apps environment and the two apps;
- the Static Web App on the Free tier.

The Terraform state lives in a storage account provided by the professor, so every pipeline run sees the same state and two runs cannot apply at once. Everything is pay-per-use. An idle system costs only the databases' storage: no Log Analytics workspace (it bills per GB), no Azure container registry.

Two design points follow from scale to zero:

- **Cold starts are expected.** The first request after a quiet period starts a container, which may find its database paused: up to about a minute of error 40613. `db.py` retries with backoff (about 90 seconds), the UI waits up to 90 seconds before showing an error, and the post-deploy check allows 3 minutes. A call to the other service keeps its 2-second timeout. If that service is still at zero replicas, the call degrades exactly as if it were down, and wakes it for the next request.
- **Nothing polls the database.** No health probe calls `/health`, because it writes to the database and would keep it from ever pausing. `max_replicas = 1` also means the migrations that run at startup can never run twice at once.

The Container Apps environment is the one resource beyond the brief's allowance (2 Container Apps, 2 serverless databases, 1 Static Web App). Container Apps cannot run without one, the brief's own `system.yaml` example names it, and on the Consumption plan it costs nothing by itself (ADR-8).

[EVIDENCE: Azure portal screenshot of `rg-sdd-3a` filtered to `jelaawar`, showing the Container Apps environment, both Container Apps, the SQL server, both databases and the Static Web App, and nothing else]

[EVIDENCE: screenshot of a Container App's "Scale" page showing min 0 / max 1 replicas, and of a database's "Compute + storage" page showing serverless with auto-pause after 15 minutes]

## 4. Database per service

Each diagram matches the service's migrations: `001_init.sql`, plus `002_add_contact_name.sql` for routing.

```mermaid
erDiagram
  ROLES ||--o{ MEMBERS : has
  ROLES ||--o{ KPI_DEFINITIONS : defines
  KPI_DEFINITIONS ||--o{ KPI_TARGETS : "target for"
  MEMBERS ||--o{ KPI_TARGETS : "set for"
  ROLES {
    int id PK
    nvarchar name UK
  }
  MEMBERS {
    int id PK
    nvarchar name
    nvarchar email UK
    int role_id FK
    bit active
  }
  KPI_DEFINITIONS {
    int id PK
    int role_id FK
    nvarchar name "unique per role"
    nvarchar metric
    nvarchar description
  }
  KPI_TARGETS {
    int id PK
    int kpi_id FK
    int member_id FK
    int year
    int quarter "1-4"
    int target_value ">= 0"
  }
```

*KPI database (`jelaawar-ieu2023-kpi-db`, user `kpi_svc`).*

```mermaid
erDiagram
  LEADS ||--o{ LEAD_OUTCOMES : records
  LEADS {
    int id PK
    nvarchar contact_name "added by 002"
    nvarchar source
    int score "0-100"
    int assigned_member_id "KPI member id, no FK"
    datetime2 assigned_at
    datetime2 created_at
  }
  LEAD_OUTCOMES {
    int id PK
    int lead_id FK
    nvarchar outcome "none, showing_booked, showing_performed, closed"
    datetime2 recorded_at
  }
```

*Routing database (`jelaawar-ieu2023-routing-db`, user `routing_svc`).* Both databases also hold `schema_migrations(version, applied_at)`. `assigned_member_id` points into the other database, so it cannot have a foreign key (ADR-3, ADR-7).

## 5. Migration evidence on Azure

The first deploy ran only `001` in each database, and the demo seed filled them. Migration `002_add_contact_name.sql` was held back in `later/` until Azure held that data. It changes a table that already holds rows:

1. it adds `leads.contact_name` as nullable,
2. it fills every existing row with `Lead #<id>`,
3. it makes the column `NOT NULL`.

The three steps are separate `GO` batches inside one transaction, so a failure leaves nothing half done. The same change was rehearsed locally on a database already holding the 30 demo leads (30 leads kept, all filled in), and a test runs it against real rows in CI.

| Step | Evidence |
| --- | --- |
| Data before 002 | [EVIDENCE: routing `GET /leads` JSON or Leads page screenshot from Azure: lead ids, sources, scores, no contact_name] |
| Deployment run | [EVIDENCE: link to the CD run that deployed 002, and its commit SHA] |
| Startup log line | [EVIDENCE: `az containerapp logs show -g rg-sdd-3a -n jelaawar-ieu2023-routing --type console --tail 300 \| grep migrat` showing `applied migration 002_add_contact_name.sql`, once] |
| Data after 002 | [EVIDENCE: the same leads, same ids, sources and scores, now with `contact_name = "Lead #<id>"`; plus a new lead created with a real contact name] |
| Second boot applies nothing | [EVIDENCE: log line `migrations up to date (2 applied)` after a restart or the next deploy] |

The recovery plan for a bad migration is in ADR-7. Migrations are forward-only: a failing file rolls back and is not recorded, and the fix is a new commit through the pipeline. Damaged data is restored from Azure SQL's point-in-time backups into a new database and copied back.

## 6. Partial failure: what a user sees

With one service stopped, the other keeps serving its own domain, and the flow across the seam degrades in a designed way. CI checks this on every push: it stops each service in the compose stack and runs the integration tests against the result.

| Situation | What the user sees | Evidence |
| --- | --- | --- |
| Routing stopped, Dashboard | Every target still listed. Actuals show "unavailable", with the banner "Routing service unavailable: targets are shown without actuals." The API answers 200 with `activity_available: false`. | [EVIDENCE: screenshot of the dashboard with routing stopped, plus the JSON of KPI `GET /dashboard`] |
| Routing stopped, Leads page | A clear error banner instead of a blank page. The browser's call to the stopped service fails at once (connection refused), and the UI turns it into "Could not reach the routing service", without hanging. | [EVIDENCE: screenshot] |
| KPI stopped, Add lead | The lead is saved. The result card says "Saved without a broker: KPI service unavailable", and the API answers 201 with `assignment: "skipped"`. | [EVIDENCE: screenshot of the result card, plus the JSON] |
| KPI stopped, Leads / Leaderboard | Brokers appear as `#id`, with a "Broker names unavailable" notice. The leaderboard notice says it ranks every member with leads. | [EVIDENCE: screenshot] |

[EVIDENCE: say where each screenshot was taken: local compose (`docker compose stop routing`), or Azure (`az containerapp revision deactivate` on one app, then activate it again)]

## 7. Pipeline evidence

```mermaid
flowchart TB
  P[push or pull request] --> CI
  subgraph CI["CI (.github/workflows/ci.yml): every push and PR"]
    direction LR
    S1["kpi + routing (matrix)<br/>ruff · pytest vs SQL Server container<br/>coverage ≥ 70% · docker build"]
    S2["integration<br/>compose stack: both up,<br/>routing stopped, kpi stopped,<br/>restart applies no migration"]
    S3[terraform fmt + validate]
    S4[OpenAPI + system.yaml schema<br/>+ actionlint]
    S1 --> S2
  end
  CI -- "success, push to main (workflow_run)" --> CD
  subgraph CD["CD (.github/workflows/cd.yml): the commit CI tested"]
    direction LR
    D1[images: build + push<br/>ghcr.io/…/kpi:SHA, routing:SHA] --> D2[terraform apply<br/>databases first]
    D2 --> D3[create/update DB users<br/>temporary firewall rule]
    D3 --> D4[terraform plan + apply<br/>Container Apps → :SHA]
    D4 --> D5[config.js + deploy ui/<br/>to the Static Web App]
    D5 --> D6[poll both /health ≤ 3 min<br/>200 and version = SHA]
  end
```


| What | Evidence |
| --- | --- |
| CI passing on the split branch (all jobs: kpi, routing, integration, terraform, specs) | https://github.com/Jadelaawar42027/devops-teamManagement/actions/runs/44559386428 (commit `d498084`) |
| Successful CD run on `main` | [EVIDENCE: link to the CD run, showing images pushed with the SHA tag, terraform apply, DB users, deploy, and the health check passing] |
| A failed run that was fixed, and its cause | [EVIDENCE: link to the failed run, one sentence on the cause, link to the fixing commit and the green run after it] |
| SHA-tagged images | [EVIDENCE: GHCR package page showing `kpi:<sha>` and `routing:<sha>`] |

**What CI gates on** (ADR-9):

- per service: ruff, then pytest against a SQL Server 2022 container, with coverage of `service.py` and `migrate.py` failing under 70% (both are at 100%: kpi 91 tests, routing 93), then `docker build`;
- the cross-seam integration test on the real compose stack, run with both services up, with routing stopped and with KPI stopped, plus a check that a restart applies no migrations;
- `terraform fmt` and `validate`;
- OpenAPI validation of both documents, `system.yaml` against `system.schema.json`, and actionlint.

CI never connects to Azure SQL. **CD** starts only after CI succeeded for a push to `main`, and deploys exactly that commit's SHA. Secrets (the service principal, the SQL passwords) live only in GitHub secrets. On Azure the database URLs are Container App secrets, never plain environment variables.

## 8. Decisions and limits

- **Hosting** (ADR-8): everything is pay-per-use and scales to zero, paid for with cold starts of up to about a minute. At 100x traffic: a minimum of one replica and more maximum replicas, migrations moved into a pipeline step so replicas cannot race, auto-pause off, and a cache for the dashboard.
- **No login** (ADR-10): the public deployment has no authentication and holds demo data only. Entra ID sign-in, with both services checking the token, comes as soon as real data goes in.
- **Not tested automatically:** the browser UI (checked by hand at desktop and mobile widths), Terraform against real Azure, and a real resume from auto-pause.

## 9. AI disclosure

[EVIDENCE: replace with the exact AI-disclosure statement required by the syllabus, as used in Assignment 1. Draft:] I used Claude Code throughout this assignment, to write and revise code, tests, Dockerfiles, Terraform, workflows and drafts of the documentation. Every prompt, what I accepted or changed, and an explanation of each AI-produced file in my own words are in `AI_USAGE.md`. The design decisions in `ADR.md` are mine, and I checked every file against the running system before submitting.

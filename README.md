# devops-teamManagement

A Flask app for a yacht brokerage that tracks each team member's quarterly KPI targets against what they actually achieved. It also scores incoming leads, assigns each one to a broker automatically, and ranks brokers by how their leads turn out.

## Setup

Requires Python 3.12.

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

On Windows, activate the virtual environment with `.venv\Scripts\activate` instead.

Then open http://localhost:8000. The database and its tables are created automatically on first start.

The app starts empty. To start with demo data (4 roles, 6 members, targets for 2026-Q4 and 30 leads):

```
SEED_DEMO=1 python app.py
```

Without demo data, add a role called "Broker" and a member with that role first. Leads are only assigned to active members with the Broker role.

## Environment variables

All are optional.

| Variable | Default | What it does |
| --- | --- | --- |
| `PORT` | `8000` | Port the app listens on. It binds to 0.0.0.0. |
| `DATA_DIR` | `data/` inside the project folder | Folder that holds the SQLite file `app.db`. Created if missing. |
| `SEED_DEMO` | not set | When set to `1`, inserts demo data on startup, but only if the members table is empty. |

## Branching workflow

Work is done on feature branches. Each branch is merged into `main` through a pull request.

## Tests and coverage

```
pytest --cov=kpi.service --cov=routing.service --cov-report=term-missing
```

Result: 65 tests pass, with 100% coverage on both `kpi/service.py` and `routing/service.py`.

The routes, templates and `seed.py` have no automated tests. See ADR-4 in `ADR.md` for why.

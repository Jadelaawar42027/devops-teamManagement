# Project: Brokerage Team KPI & Lead Routing (IE DevOps Assignment 1)

Single-process Flask app for a yacht brokerage with two domains.
- Domain 1 "kpi": roles, members, KPI definitions, quarterly targets, and KPI actuals calculated on read.
- Domain 2 "routing": leads (score 0-100, banded hot >=70, warm 40-69, cold <40), lead outcomes (none=0, showing_booked=1, showing_performed=2, closed=4), a broker score, and next-broker assignment.

## Hard rules
- Python 3.12, Flask, Jinja templates, built-in sqlite3 (no ORM), pytest + pytest-cov. No other packages.
- Started with `python app.py`, binds 0.0.0.0, port from PORT (default 8000), SQLite at $DATA_DIR/app.db (default ./data).
- Tables created automatically on startup. All config via env vars. No .env file required.
- Structure: app.py, db.py, schema.sql, kpi/ (routes.py, service.py), routing/ (routes.py, service.py), templates/, tests/.
- kpi must never import routing's database code. The only link is routing.service.activity_counts().
- No Dockerfile, CI workflows, or infrastructure code.

## Code style
- Simple and readable, like a competent student wrote it.
- No comments or docstrings unless the logic is genuinely non-obvious.
- No over-engineering, no classes where functions work, no type-hint clutter.

## How to work with me
- Never run git commands. I make all commits and pushes myself.
- Do only the step I give you. Don't create files or tests for later steps early.
- After each step, run the app or pytest to check it works, and tell me what you ran.
- After each step, explain in 3-5 sentences how the code works using the actual function and variable names, so I can explain it myself on paper.
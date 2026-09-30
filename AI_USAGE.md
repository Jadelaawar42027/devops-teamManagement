# AI Usage Log

| Date/commit | Tool | Prompt | Disposition (Accepted/Modified/Rejected) | What changed & why (if modified) | In my own words, how this works |
|---|---|---|---|---|---|
| 2026-09-30 | Claude Code | Step 1: create app.py, requirements.txt and .gitignore. app.py reads PORT and DATA_DIR from env with defaults, makes sure DATA_DIR exists, runs on 0.0.0.0, and has a placeholder "/" route. | Accepted | | |
| 2026-09-30 | Claude Code | Step 2: create schema.sql with six tables (roles, members, kpi_definitions, kpi_targets, leads, lead_outcomes), with leads.assigned_member_id having no foreign key to members. Create db.py with get_connection() and init_db(), and call init_db() on startup. | Accepted | | |

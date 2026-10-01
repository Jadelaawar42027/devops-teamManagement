# Architecture Decision Records

## 1. Use Flask as the web framework
Date: 2026-09-30
Status: Decided
Context: The app needs a backend that can serve HTML pages and handle forms, with two separate feature areas (team/KPIs and lead routing), running as one process with SQLite. The deadline is under a week, so the framework has to be something I can build in quickly and explain line by line.
Decision: Flask, with Jinja templates and Python's built-in sqlite3, because it's small: a route is just a function, so there's very little hidden "magic" to explain, and I already know Python. Its blueprints let me give each domain its own folder and routes, which matches the two-domain split.
Alternatives considered:
- Django: it comes with an admin panel, its own ORM, a user/auth system and a fixed project layout. I'd use almost none of it. It is also built around its ORM and migrations, so writing raw SQL to show my schema decisions directly would mean working against the framework.
- FastAPI: it's designed for JSON APIs with automatic API docs. My app mainly serves HTML pages to staff, so those strengths don't help much, and it needs extra packages (uvicorn to run it, python-multipart for forms) that add dependencies for no benefit to this app, while Flask has its own dev server and handles forms out of the box.

Consequences: Each domain is self-contained, so it can be lifted out into its own service in Assignment 2 with little change (the in-process activity_counts() call would become an HTTP call), and the app starts well within the deployment contract's "within a few seconds" limit. The cost is that Flask gives less out of the box, so input validation, login and database migrations have to be written or added manually if the app grows, raw SQL means more code than an ORM, and Flask's built-in server is only a development server, so Assignment 2 may need a production server like gunicorn.

## 3. Calculate KPI actuals on read, and no foreign key from leads to members
Date: 2026-10-01
Status: Decided
Context: Both domains share one SQLite file. KPI actuals (leads assigned, showings booked, showings performed, deals closed) depend on data the routing domain records: lead_outcomes has no member column, so every actual is attributed to a broker through leads.assigned_member_id. A stored actual would be a second copy of that data and would go stale whenever an outcome is added or a lead is reassigned. The schema also has to keep the two domains separable for Assignment 2.
Decision: Six tables: four owned by the KPI domain (roles, members, kpi_definitions, kpi_targets) and two by routing (leads, lead_outcomes). Roles are rows in a roles table, linked by role_id from members and kpi_definitions. kpi_targets stores only the target; actuals are not stored anywhere. They are calculated when a KPI page is requested, from leads and lead_outcomes, through routing.service.activity_counts(), which is the only link between the domains. leads.assigned_member_id holds a member id as a plain nullable integer with no foreign key to members, even though every other reference in the schema is an enforced foreign key.
Alternatives considered:
- An actual_value column in kpi_targets, updated whenever an outcome is recorded: this creates two copies of the truth that can drift apart, for example when a lead is reassigned after its outcome was recorded. Routing code would also have to write to a KPI table, which couples the domains.
- A foreign key from leads to members: this ties routing's tables to the KPI domain's. A SQLite foreign key can't point at a table in another database file, so routing couldn't move to its own database without dropping it.
- One table per role (brokers, setters, and so on): every new role would need a new table and new queries. A roles table plus role_id handles a new role with a new row.

Consequences: KPI numbers always match the recorded outcomes with no sync code, and the routing tables can be moved out with no schema changes because neither of them references a KPI table. The cost is that actuals are recalculated on every page load. That is fine at the expected size (about 15 staff and 300 leads a month) but would need caching at a much larger scale. Without the foreign key, the database won't stop a lead from pointing at a member id that was deleted or never existed, so the app has to: members are deactivated with the active flag instead of deleted, and routing has to check the member exists before assigning a lead.

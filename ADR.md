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

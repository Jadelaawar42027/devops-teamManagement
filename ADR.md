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

## 2. Split the app into kpi and routing packages joined by one function, activity_counts()
Date: 2026-10-02
Status: Superseded by 6
Context: The app has two areas, team/KPIs and lead routing, which are expected to become separate services in Assignment 2. They can't be fully independent: every KPI actual (leads assigned, showings booked, showings performed, deals closed) comes from data the routing domain records. Without a planned boundary, KPI code would end up querying leads and lead_outcomes directly, or routing code would write into KPI tables, and a change to one domain's tables would break the other domain's code.
Decision: Each domain is its own package, kpi/ and routing/, with its own routes.py (a Flask blueprint), its own service.py and its own tables. KPI code gets routing data through exactly one function, routing.service.activity_counts(conn, member_id, quarter), where quarter is a string like "2026-Q4". It returns a dictionary with four counts for that member and quarter: leads_assigned, showings_booked, showings_performed and deals_closed. These are the same names a KPI definition stores in its metric column, so kpi_progress() in kpi/service.py looks each actual up by key and compares it to the target. A lead is counted in the quarter it was assigned, and an outcome in the quarter it was recorded. KPI code never queries leads or lead_outcomes, and routing never reads or writes a KPI table. What the two domains still share is the plumbing: one schema.sql, one app.db, the get_connection() function in db.py, and the base.html template. That sharing is also why KPI code can pass its own connection (conn) into activity_counts().
Alternatives considered:
- KPI code queries leads and lead_outcomes directly with SQL joins: it's simpler, and one join could fetch the counts for every member at once. But KPI code would depend on routing's table structure, so any column change in routing could break the KPI pages, and after the split the KPI service would need access to routing's database.
- Routing writes counts into KPI tables whenever an outcome is recorded: this makes routing depend on KPI's tables instead, which is the same coupling in the other direction. It also stores a second copy of the data that can drift out of sync (see ADR-3).

Consequences: In Assignment 2, activity_counts() can become an HTTP endpoint and the KPI service swaps one function call for one HTTP request, with no SQL to rewrite on the KPI side: the conn argument goes away and the dictionary becomes the JSON response. The shared plumbing still has to be split: schema.sql into two files, one database into two, and each service needs its own connection code and base template. The costs: the KPI dashboard calls kpi_progress(), and so activity_counts(), once per member, which is fine for about 15 staff but would need a bulk version at a larger scale. Table ownership is only a convention, because nothing in SQLite stops one domain querying the other's tables while they share a file. And activity_counts() only covers KPI reading routing's data. Routing also needs to know which members can take a lead, and it is not allowed to query the members or roles tables itself. So there is a second dependency, in the opposite direction: kpi.service.active_broker_ids(conn) returns the ids of active members with the Broker role, routing/routes.py calls it for the add-lead form and the leaderboard, and passes the ids into pick_next_broker(conn, band, broker_ids, today). routing/service.py imports nothing from kpi and only ever sees a list of ids. Assignment 2 will have to turn this into a second HTTP call, and because routing only gets ids, the leaderboard and leads pages show member ids instead of names. The ids stored in leads.assigned_member_id are still not checked by the database (see ADR-3), but they now only come from active_broker_ids().

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

## 4. Test the service modules against a real database, and leave the routes untested
Date: 2026-10-03
Status: Superseded by 9
Context: The brief requires at least 70% test coverage on the core business logic of both domains, which I take to mean kpi/service.py and routing/service.py, and the deadline is under a week. A coverage check partway through showed kpi/service.py at 0% and routing/service.py at 67% (43% combined), because tests had only been written for scoring and lead assignment. I had to choose where the remaining testing time went.
Decision: Test only the two service modules with pytest. Pure functions (score_from_results, band_for_score, parse_quarter, quarter_dates) are called directly. Everything that runs SQL is tested against a real temporary SQLite database, created fresh for each test by the conn fixture in conftest.py, with no mocking. I prioritised the logic where a mistake gives a plausible wrong answer instead of an error: broker scoring, banding and the assignment rules came first. Validation, activity_counts() and KPI progress came after the coverage check. The result is 100% on both service files from 65 tests.
Alternatives considered:
- Testing the routes with Flask's test client: the routes do contain logic of mine (add_lead() chains lead creation, banding and assignment, and the forms turn errors into messages), but they are thin wrappers around service functions that are fully tested, and the brief's target is the business logic. With limited time, the service layer came first.
- Mocking the database: much of the real logic is in the queries, like the quarter date ranges and COUNT(DISTINCT) in activity_counts(), the upsert in set_target() and the join in active_broker_ids(). A mock would test none of that. There was also little speed to gain, because the whole suite runs in under a second against real SQLite.

Consequences: The business rules are protected, so the service code can be restructured for the Assignment 2 split with the tests as a safety net. Most tests will carry over unchanged, but the kpi_progress() tests set up their data by inserting into routing's leads table, so they will need rewriting once activity_counts() is an HTTP call. The cost is that app.py, both routes.py files, the templates and seed.py have no automated tests: counting those files, coverage of the application code is about 41% (163 of 395 statements). Form handling, the auto-assign wiring in add_lead() and the dashboard's default quarter are only checked by hand. The KPI tests were also written late, after all the KPI code existed. Next time, tests should be written alongside each feature, not after a coverage check.

## 5. Build two domains in depth and leave out contracts, tasks, login and CRM sync
Date: 2026-10-03
Status: Superseded by 10
Context: A real brokerage would also want contracts, task management, login with permissions, and CRM integration, but I had five days. The brief rewards depth in two domains over breadth, and the deployment contract forbids depending on private external services, which rules out CRM sync in particular. Contracts and task management could have been built inside the app, so for those the limit was time alone.
Decision: Build only the two domains, team KPIs and lead routing, and not build contracts, task management, login and permissions, CRM sync, or automatic scoring of leads. The inputs are entered by hand: members, targets, leads, each lead's 0-100 score, and outcomes. What the app works out itself is the lead's band, which broker gets it, each broker's score, and the KPI actuals. There are no user accounts and no route checks who is calling, so the app assumes it is only reachable on an internal network.
Alternatives considered:
- Contracts and tasks as extra features: they would add tables and forms but little new logic compared with scoring and assignment. The brief gives a third feature only a small amount of credit, and the time would have come out of tests and documentation.
- CRM sync: it needs credentials for a private service, so nobody without them, including the grader, could run or check it, and it could not be covered by the tests. It would also work against the requirement that the app runs cleanly on a fresh clone with no external dependencies.
- Login: Flask's built-in sessions and Werkzeug's password hashing mean it needs no extra package, but it does need a users table, a first-user setup step, a check on every route, and a secret key, which would either become a required env var or log everyone out on each restart. None of that serves the two core domains.

Consequences: The time went into the scoring and assignment logic, 100% coverage of the service modules, and the documentation. The cost is that anyone who can reach the app can view and edit everything. It binds 0.0.0.0, so that means anyone on the same network, and nothing in the app enforces the internal-network assumption. Login must be added before the public Azure deployment in Assignment 2. Data entry is manual, including each lead's score. A CRM webhook that creates leads automatically is the most valuable next feature, but it depends on things left out here: an open endpoint that creates leads needs authentication first, each lead needs a score sent by the CRM or calculated by the app, and the leads table has no external id to stop the same CRM lead being created twice.

## 6. Split along the ADR-2 seam, with two server-side HTTP calls that degrade instead of failing
Date: 2026-11-19
Status: Draft
Context: Assignment 2 turns the monolith into two services, each with its own container and database, talking over HTTP. ADR-2 drew the seam between team/KPIs and lead routing and limited what crossed it to two in-process calls: KPI read routing's counts through activity_counts(), and routing read the active brokers through active_broker_ids(). Now each call is an HTTP request that can time out or find the other service stopped, and the brief requires at least one flow to cross the seam server side and every failure to be handled.
Decision: Keep the seam where ADR-2 put it. The KPI service owns roles, members, kpi_definitions and kpi_targets. The routing service owns leads and lead_outcomes. Exactly two endpoints cross the seam, and both calls are made server side:
- KPI's GET /dashboard calls routing's GET /activity?quarter=&member_ids=, one call for every member with a target, instead of ADR-2's one call per member.
- Routing's POST /leads and GET /leaderboard call KPI's GET /brokers/active.
Each service finds the other through an environment variable (ROUTING_URL, KPI_URL), and every call has a 2-second timeout (ROUTING_TIMEOUT_S, KPI_TIMEOUT_S). When the other side is unreachable, times out, or answers anything but 200, the caller degrades instead of failing:
- The dashboard still shows every target, with actual and percent set to null and a notice.
- A new lead is saved without a broker (assignment "skipped") and a notice says so.
- The leaderboard ranks every member who has leads, with a notice.
The UI joins broker names client side from KPI's GET /members, and shows "#id" when KPI is down.
Alternatives considered:
- Let the UI call both services and combine the results for the dashboard: this works without any server-to-server call, but the brief needs one server-side flow, and matching each target's metric to a count is KPI's business logic, which would then live in JavaScript.
- Keep one /activity call per member, as ADR-2 planned: with routing down, each call waits for its own timeout, so 15 members could make the dashboard hang for 30 seconds. One bulk call waits at most 2 seconds and is one round trip when routing is up.
- Retry, or cache the last good answer: a retry doubles the wait when the other service really is down. A cache would show old numbers as if they were current, and would need storage of its own. Showing the targets with a clear "actuals unavailable" notice is honest and needs neither.
- Move the seam, for example by giving routing a copy of the members: that is the duplicated data ADR-3 rejected, and it would have to be kept in sync across two databases.
Consequences: ADR-2 held. The two functions it named became the only two endpoints that cross the seam, and no SQL had to be rewritten across it. The bulk /activity endpoint is a change from ADR-2, and it is capped at 200 member ids per call. Each service keeps working on its own domain when the other is stopped, which the integration test checks (ADR-9). The cost is weaker consistency at the edges. A lead saved while KPI is down stays unassigned until someone assigns it, because nothing retries it later. The leaderboard fallback can include inactive brokers. And the dashboard's numbers depend on two databases being read at slightly different moments.

## 7. One database and login per service, a numbered-SQL migration runner, and forward-only recovery
Date: 2026-11-19
Status: Draft
Context: Assignment 1 had one SQLite file created from schema.sql on first boot. Now each service needs its own SQL Server database that only it can open, and the schema has to change in place once a database holds data. A migration runs on startup against the live database, so a bad one would hit real rows.
Decision: Each service has its own database and its own user. Locally that is db/init.sql, which is idempotent and creates the kpi and routing databases with a kpi_svc and a routing_svc login, each a user in its own database only. On Azure, the pipeline creates contained users with infra/scripts/create_db_users.py. These are users that exist only inside their database, with no server login, created through the server admin, which the apps never use. Each user is db_owner of its own database, because each service runs its own migrations.
The SQLite schema was ported by hand: INTEGER PRIMARY KEY AUTOINCREMENT became INT IDENTITY, TEXT became NVARCHAR, text dates became DATETIME2 with SYSUTCDATETIME() defaults, lastrowid became OUTPUT INSERTED.id, and the upsert became an UPDATE followed by an INSERT when no row was updated.
Migrations are numbered SQL files in each service's migrations/ folder, run by a small runner of my own (migrate.py) when the service starts:
- every applied file is recorded in schema_migrations, so a second start applies nothing;
- each file runs in one transaction, so a failing file is rolled back completely and is not recorded;
- a line containing only GO splits a file into batches, because SQL Server cannot use a column added by ALTER TABLE in the same batch.
gunicorn --preload runs migrations once per container, not once per worker. There is exactly one container per service, so migrations never run twice at the same time.
No data had to move. The Assignment 1 database only ever held local demo data, so the new databases start empty and the idempotent demo seed fills them.
Alternatives considered:
- Alembic: it works without an ORM, but it adds a package and its own revision chain to learn and explain, while the migrations I need are plain SQL. My runner is about 70 lines, and its tests cover running once, rollback, and a column added and backfilled in a table that holds data.
- One shared database with a schema per service: it is cheaper, but one login could be granted both schemas by mistake. The brief also requires one serverless database per service.
- Running migrations from the pipeline instead of at startup: this is safer once there is more than one replica (see ADR-8), but it needs a migration step with database access from GitHub. With one container per service, running them at startup is simpler.
Consequences: Integrity lost at the seam: leads.assigned_member_id points into another database, so no foreign key can check it (ADR-3 already left it out for this reason). It is compensated in code: routing only assigns ids it just received from KPI's /brokers/active, and KPI never deletes members, it only deactivates them, so an id on a lead always names a member who existed.
Recovery plan for a bad migration (forward-only, no down-migrations):
1. A migration that fails is rolled back by its transaction and is not recorded. The service does not start and its container keeps restarting, while the other service keeps working (ADR-6). The fix is a new commit through CI and CD. Because the failed file never ran anywhere, it may be corrected in place if it also never succeeded in CI or locally; otherwise the fix is a new numbered file.
2. A migration that succeeds but damages data is never edited. The correction is a new numbered migration. If rows were lost, Azure SQL's automatic backups allow a point-in-time restore of the database to a new database from before the deploy, and the lost rows are copied back from it.
3. Before a migration that changes existing data, I take the data-before evidence and keep the restore point in mind. later/002_add_contact_name.sql is held back until Azure already holds data, for exactly this reason.

## 8. Serverless on Azure: Container Apps, Azure SQL serverless and a Static Web App, created by Terraform
Date: 2026-11-20
Status: Draft
Context: The brief (§1a, §7) fixes the hosting: both services on Azure Container Apps (Consumption plan, scaling to zero), one serverless Azure SQL database per service on one logical server, and the UI on one Azure Static Web App. Only pay-per-use resources are allowed; anything with a fixed monthly cost needs a justification here. Each student may create at most 2 Container Apps, 2 serverless databases and 1 Static Web App in the shared class resource group, "not even temporarily". The free choice is how the infrastructure is defined: Azure CLI commands in the workflow, or IaC.
Decision: Terraform in infra/terraform creates, in the class resource group, read through a data source and never created:
- the logical server jelaawar-ieu2023-sql and two serverless databases, jelaawar-ieu2023-kpi-db and jelaawar-ieu2023-routing-db: GP_S_Gen5_1 (0.5 to 1 vCore), auto-pause after 15 minutes (the shortest Azure allows; the provider rejects 14), 2 GB, locally redundant backups. The firewall allows Azure services only;
- the Container Apps environment jelaawar-ieu2023-env on the Consumption plan, and the two apps jelaawar-ieu2023-kpi and jelaawar-ieu2023-routing. Each has public HTTPS ingress, min 0 and max 1 replicas, the image tagged with the commit SHA from GHCR, its DATABASE_URL as a Container App secret, and CORS_ORIGINS set to the Static Web App's origin;
- the Static Web App jelaawar-ieu2023-ui on the Free tier, whose URL is the public URL of the system.
The environment is the one resource the brief does not list among the allowance. Container Apps cannot exist without one, the brief's own system.yaml names it (<prefix>-env), and on the Consumption plan it costs nothing by itself. Nothing else is created:
- no Log Analytics workspace, which bills per GB; logs are streamed live with az containerapp logs show;
- no Azure Container Registry, because GHCR is free;
- no storage of my own: the Terraform state lives where the professor provides it.
The PDF and the provided system.schema.json conflict on UI hosting. The PDF (§1a, §5, §7.1, §7.2, §7.6, the one-Static-Web-App allowance, and the grading line "UI deployed to Static Web Apps") requires a Static Web App, and its own system.yaml example uses ui.static_web_app. The schema instead requires ui.storage_account, a Storage static website, and rejects any other field. I follow the PDF, so system.yaml truthfully names the Static Web App. CI still validates system.yaml against the provided schema, through a copy with exactly one allowance: the ui object may have static_web_app instead of storage_account, and exactly one of the two. That copy is made by scripts/patch_schema_for_swa.py, and every other constraint stays as it is, including additionalProperties: false. The CI log prints the diff. system.schema.json itself is untouched. If a corrected schema is provided, the script detects it and the patch step is removed.
Alternatives considered:
- Azure CLI commands in the workflow: imperative, so a second run fails or duplicates resources unless every command checks first, and there is no plan to read before a change is applied. Terraform compares the code with the state and changes only the difference, and the same files document the infrastructure.
- Bicep: also declarative and Azure-native, with no state file to host. But Terraform's plan output and state make each change explicit, and the same tool works beyond Azure.
- A VM behind a load balancer with a DNS zone: an earlier draft of mine built this, and I removed it. The brief puts virtual machines out of scope as always-on compute, and the load balancer and VM cost money every hour.
Consequences: Cost model: everything bills only while used.
- Container Apps bill per second of vCPU and memory while a replica runs, inside a monthly free grant, and nothing at zero replicas.
- The databases bill compute per second while running (0.5 vCore minimum) and only storage while paused.
- The Static Web App is free.
An idle system costs only the databases' storage (TODO: check with the Azure pricing calculator).
Scale to zero for the containers: the first request after a quiet period waits for a container to start. Scale to zero for the database: the database may be paused, and resuming takes up to about a minute, with connections refused meanwhile (error 40613).
- db.py retries with exponential backoff (DB_CONNECT_RETRIES=10, about 90 seconds).
- Migrations run at startup, before gunicorn answers. With max_replicas 1 they can never run twice at once.
- The UI waits up to 90 seconds before showing an error, and the pipeline's health check allows 3 minutes.
- Calls between the services keep their 2-second timeout. So when the other app is still at zero replicas, the first dashboard or new lead degrades as if it were down (ADR-6), and that call wakes it for the next request.
- No health probe calls /health, because it writes to the database and would keep it from ever pausing.
At 100x traffic:
- min_replicas 1 or more, so there are no cold starts, and max_replicas above 1;
- migrations moved from startup into one pipeline step, because replicas would race;
- auto-pause turned off, with more vCores;
- a cache for the dashboard's activity counts;
- the calls between the services moved to internal ingress, instead of going out and back in through the public one.

## 10. Still no login: the public deployment runs without authentication
Date: 2026-11-19
Status: Draft
Context: ADR-5 left login out of Assignment 1 and said it "must be added before the public Azure deployment in Assignment 2". That deployment now exists. The UI is a public Static Web App, and both services have public HTTPS URLs, because the browser calls them directly (ADR-8). Every route is open, so anyone who finds a URL can:
- read the team, its targets and every lead;
- add members and leads, change targets, deactivate members and record outcomes.
Nothing can be deleted: members are only deactivated, and leads have no delete endpoint. Migration 002 adds the name of the person behind each lead, which makes the leads table personal data once real names go in. The brief requires no new features, and the deadline is three days away.
Decision: Do not build authentication in this assignment. Keep the system to demo data only: invented names, @example.com emails, and leads made by the seed or by hand, never real customers. Superseding ADR-5's consequence, the deployment goes public without login, and this entry records the risk and the conditions for building it.
The reason is that a login that is not a toy is a third feature area, larger than either domain:
- The UI is static and lives on a different origin from the two services. A cookie session set by one service would not reach the other, so it needs tokens: the UI signs the user in, and sends a token that both services verify on every request.
- It also needs CORS with credentials, a way to give the professor and graders access, and roles if managers and brokers should see different things.
- Doing it properly means a central identity provider, Microsoft Entra ID, which needs an app registration in the IE tenant. Neither the class service principal nor a student account can create one.
- The brief puts the credit on the split, the pipeline and the deployment.
Alternatives considered:
- Container Apps' built-in authentication ("Easy Auth") with Entra ID: no code in the services, but it still needs the app registration. It is also built for pages served by the app itself, so a static UI on another origin would still need tokens.
- The Static Web App's built-in login (GitHub or Microsoft accounts, available on the Free tier): it protects the UI's files, but not the two Container Apps, which the browser calls directly on other origins. Putting the services behind the Static Web App as "linked backends" needs the Standard tier, a fixed monthly cost.
- One shared password checked by both services (an API key in a header): simple, but the key would have to live in the static UI's JavaScript, where anyone can read it. It hides the app rather than securing it.
- Username and password login inside each service, with signed tokens: the most control, and the most code: a users table, password hashing, token signing and checking in both services, and changes to every endpoint in both OpenAPI documents.
- IP restrictions on the Container Apps' ingress: cheap, but the graders' addresses are unknown, and the brief requires the live URL to stay reachable.
Consequences: Anyone can change the demo data before or during grading. Recovery is easy but manual: a member can be reactivated only through SQL, wrong targets can be overwritten, and junk leads stay. Bots that find the Static Web App cost nothing, but any that call a service start a Container App and wake its database, which bills while it runs (ADR-8). No real or personal data may be entered while this holds.
I would build authentication as soon as any one of these is true:
1. real customer or staff data goes in, at the latest with the contact names from migration 002;
2. the app is used by anyone outside this assignment, or stays online after grading;
3. different people need different rights, for example managers set targets while brokers only record outcomes.
The order would be:
1. an Entra ID app registration, requested from IT, with sign-in in the UI (Microsoft's MSAL library);
2. both services checking the Entra ID token on every request except /health, through a small shared check in web.py;
3. a roles claim or a roles table in KPI, if the rights in condition 3 are needed.
HTTPS is already in place on every part of the system.

Held back on purpose (assignment §4.3 and §4.6): the first deploy to Azure runs only migration
001, so the demo data lands in the routing database first. Only THEN apply this, so the report
can show the same rows before and after a migration that changes a table holding data.

What is here
  002_add_contact_name.sql   the migration: adds leads.contact_name, backfills existing rows with
                             "Lead #<id>", then makes the column NOT NULL (three GO batches, one
                             transaction)
  002-contact-name.patch     everything else that has to change with it, tested together:
                             routing service.py (create_lead takes and validates contact_name),
                             app.py (POST /leads requires it), seed.py (demo leads get names),
                             openapi.yaml, the routing tests (plus a test that runs 001, inserts
                             leads, runs 002 and checks the backfill), the integration test, and
                             the UI (form field, Contact column, lead detail)

Before applying
  1. The live app on Azure shows demo leads (<routing_url>/leads returns 30; routing_url is
     printed by the CD run, or: az containerapp show -g rg-sdd-3a -n jelaawar-ieu2023-routing
     --query properties.configuration.ingress.fqdn -o tsv).
  2. Take the "before" evidence: a screenshot of the Leads page, and the JSON of the leads
     saved to a file (curl -s https://<routing fqdn>/leads > before.json).

Apply (from the repository root, on a new branch)
  git switch -c migration-002-contact-name
  git mv later/002_add_contact_name.sql services/routing/migrations/002_add_contact_name.sql
  git apply later/002-contact-name.patch
  git rm later/002-contact-name.patch later/README.txt

Check locally
  cd services/routing && DATABASE_URL='mssql://sa:...@localhost:11433/master' pytest --cov
  docker compose up -d --build   (the local database already has data: routing's log shows
                                  "applied migration 002_add_contact_name.sql" once, and old
                                  leads show "Lead #<id>" as their contact)

Then commit, push, open a PR, and merge. CD deploys it. Take the "after" evidence: the CD run
link, the routing startup log line
  (az containerapp logs show -g rg-sdd-3a -n jelaawar-ieu2023-routing --type console --tail 300 | grep migrat),
and the leads again (same ids, sources and scores, now with contact_name).

import logging
import os
from datetime import datetime, timezone

from flask import Flask, jsonify, request

import db
import kpi_client
import service
import web
from migrate import run_migrations
from seed import seed_demo

MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations")
MAX_MEMBER_IDS = 200


def utc_today():
    # SQL Server's SYSUTCDATETIME() is UTC, so lead ages are measured against the UTC date
    return datetime.now(timezone.utc).date()


def body():
    return request.get_json(silent=True) or {}


def bad_request(message):
    return jsonify(error=message), 400


def create_app(migrate=True):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    if migrate:
        conn = db.get_connection()
        try:
            run_migrations(conn, MIGRATIONS_DIR)
            if os.environ.get("SEED_DEMO") == "1":
                seed_demo(conn)
        finally:
            conn.close()

    app = Flask(__name__)
    web.install(app)

    def with_conn(fn, *args):
        conn = db.get_connection()
        try:
            return fn(conn, *args)
        finally:
            conn.close()

    @app.get("/leads")
    def leads():
        return jsonify(leads=with_conn(service.list_leads))

    @app.post("/leads")
    def add_lead():
        # the second flow across the seam: routing asks KPI who the active brokers are
        data = body()
        source = str(data.get("source", "")).strip()
        try:
            score = int(data.get("score"))
        except (TypeError, ValueError):
            return bad_request("score must be a whole number from 0 to 100")
        if not source:
            return bad_request("source is required")
        conn = db.get_connection()
        try:
            try:
                lead_id = service.create_lead(conn, source, score)
            except ValueError as exc:
                return bad_request(str(exc))
            band = service.band_for_score(score)
            assignment = "assigned"
            notice = None
            try:
                broker_ids = kpi_client.active_broker_ids()
            except kpi_client.KpiUnavailable:
                # degrade: the lead is never lost, it is saved unassigned and can be assigned later
                broker_ids = None
                assignment = "skipped"
                notice = "KPI service unavailable: lead saved without a broker."
            if broker_ids is not None:
                member_id = service.pick_next_broker(conn, band, broker_ids, utc_today())
                if member_id is None:
                    assignment = "no_brokers"
                    notice = "No active brokers: lead saved without a broker."
                else:
                    service.assign_lead(conn, lead_id, member_id)
            lead = service.get_lead(conn, lead_id)
        finally:
            conn.close()
        return jsonify(lead=lead, band=band, assignment=assignment, notice=notice), 201

    @app.get("/leads/<int:lead_id>")
    def lead(lead_id):
        found = with_conn(service.get_lead, lead_id)
        if found is None:
            return jsonify(error="lead not found"), 404
        result = dict(found)
        result["band"] = service.band_for_score(found["score"])
        result["outcomes"] = with_conn(service.list_outcomes, lead_id)
        return jsonify(result)

    @app.post("/leads/<int:lead_id>/outcomes")
    def add_outcome(lead_id):
        try:
            with_conn(service.record_outcome, lead_id, str(body().get("stage", "")))
        except LookupError:
            return jsonify(error="lead not found"), 404
        except ValueError as exc:
            return bad_request(str(exc))
        return jsonify(outcomes=with_conn(service.list_outcomes, lead_id)), 201

    @app.get("/leaderboard")
    def leaderboard():
        notice = None
        try:
            broker_ids = kpi_client.active_broker_ids()
        except kpi_client.KpiUnavailable:
            # degrade: rank everyone who has ever been assigned a lead, which may include inactive brokers
            broker_ids = with_conn(service.assigned_member_ids)
            notice = "KPI service unavailable: showing every member with leads, including any who are inactive."
        rows = with_conn(service.leaderboard, broker_ids, utc_today())
        return jsonify(brokers=rows, notice=notice)

    @app.get("/activity")
    def activity():
        # called by the KPI service for its dashboard
        quarter = request.args.get("quarter", "")
        try:
            service.quarter_dates(quarter)
            raw = request.args.get("member_ids", "")
            member_ids = [int(part) for part in raw.split(",") if part.strip()]
        except ValueError as exc:
            return bad_request(str(exc) if "quarter" in str(exc) else "member_ids must be comma-separated numbers")
        if len(member_ids) > MAX_MEMBER_IDS:
            return bad_request(f"at most {MAX_MEMBER_IDS} member_ids per call")
        counts = with_conn(service.activity_counts_bulk, member_ids, quarter)
        return jsonify(quarter=quarter, members={str(k): v for k, v in counts.items()})

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))

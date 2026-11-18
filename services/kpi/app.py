import logging
import os
from datetime import datetime, timezone

import pymssql
from flask import Flask, jsonify, request

import db
import routing_client
import service
import web
from migrate import run_migrations
from seed import seed_demo

MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations")


def current_quarter():
    today = datetime.now(timezone.utc).date()
    return f"{today.year}-Q{(today.month - 1) // 3 + 1}"


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

    @app.get("/roles")
    def roles():
        return jsonify(roles=with_conn(service.list_roles))

    @app.post("/roles")
    def add_role():
        name = str(body().get("name", "")).strip()
        if not name:
            return bad_request("name is required")
        try:
            role_id = with_conn(service.create_role, name)
        except pymssql.IntegrityError:
            return jsonify(error="a role with that name already exists"), 409
        return jsonify(id=role_id, name=name), 201

    @app.get("/members")
    def members():
        return jsonify(members=with_conn(service.list_members))

    @app.post("/members")
    def add_member():
        data = body()
        name = str(data.get("name", "")).strip()
        email = str(data.get("email", "")).strip()
        try:
            role_id = int(data.get("role_id"))
        except (TypeError, ValueError):
            return bad_request("role_id must be a number")
        if not name or "@" not in email:
            return bad_request("name and a valid email are required")
        try:
            member_id = with_conn(service.create_member, name, email, role_id)
        except pymssql.IntegrityError:
            return jsonify(error="email already used, or role does not exist"), 409
        return jsonify(with_conn(service.get_member, member_id)), 201

    @app.get("/members/<int:member_id>")
    def member(member_id):
        found = with_conn(service.get_member, member_id)
        if found is None:
            return jsonify(error="member not found"), 404
        return jsonify(found)

    @app.post("/members/<int:member_id>/deactivate")
    def deactivate(member_id):
        try:
            with_conn(service.deactivate_member, member_id)
        except ValueError:
            return jsonify(error="member not found"), 404
        return jsonify(with_conn(service.get_member, member_id))

    @app.get("/brokers/active")
    def brokers_active():
        # called by the routing service to decide who can receive a lead
        return jsonify(broker_ids=with_conn(service.active_broker_ids))

    @app.get("/members/<int:member_id>/kpis")
    def member_kpis(member_id):
        found = with_conn(service.get_member, member_id)
        if found is None:
            return jsonify(error="member not found"), 404
        return jsonify(kpis=with_conn(service.list_kpis, found["role_id"]))

    @app.post("/members/<int:member_id>/kpis")
    def add_kpi(member_id):
        data = body()
        found = with_conn(service.get_member, member_id)
        if found is None:
            return jsonify(error="member not found"), 404
        name = str(data.get("name", "")).strip()
        if not name:
            return bad_request("name is required")
        try:
            kpi_id = with_conn(service.create_kpi, found["role_id"], name, data.get("metric"), data.get("description"))
        except ValueError as exc:
            return bad_request(str(exc))
        except pymssql.IntegrityError:
            return jsonify(error="this role already has a KPI with that name"), 409
        return jsonify(id=kpi_id, role_id=found["role_id"], name=name, metric=data.get("metric")), 201

    @app.get("/members/<int:member_id>/targets")
    def targets(member_id):
        if with_conn(service.get_member, member_id) is None:
            return jsonify(error="member not found"), 404
        return jsonify(targets=with_conn(service.list_targets, member_id))

    @app.put("/members/<int:member_id>/targets")
    def put_target(member_id):
        data = body()
        try:
            kpi_id = int(data.get("kpi_id"))
            target_value = int(data.get("target_value"))
            with_conn(service.set_target, member_id, kpi_id, str(data.get("quarter", "")), target_value)
        except (TypeError, ValueError) as exc:
            return bad_request(str(exc) or "kpi_id and target_value must be numbers")
        except pymssql.IntegrityError:
            return jsonify(error="member or KPI does not exist"), 409
        return jsonify(targets=with_conn(service.list_targets, member_id))

    @app.get("/dashboard")
    def dashboard():
        # the server-side flow across the seam: targets from this database, actuals from routing
        quarter = request.args.get("quarter") or current_quarter()
        try:
            service.parse_quarter(quarter)
        except ValueError as exc:
            return bad_request(str(exc))
        conn = db.get_connection()
        try:
            members = service.list_members(conn)
            targets = {m["id"]: service.member_targets_for_quarter(conn, m["id"], quarter) for m in members}
        finally:
            conn.close()
        with_targets = [m["id"] for m in members if targets[m["id"]]]
        activity_available = True
        notice = None
        try:
            activity = routing_client.activity_for_members(with_targets, quarter)
        except routing_client.RoutingUnavailable:
            activity_available = False
            activity = {}
            notice = "Routing service unavailable: targets are shown without actuals."
        rows = []
        for m in members:
            counts = activity.get(m["id"], {}) if activity_available else None
            rows.append({"member": m, "progress": service.kpi_progress(targets[m["id"]], counts)})
        return jsonify(quarter=quarter, activity_available=activity_available, notice=notice, rows=rows)

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))

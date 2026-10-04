import sqlite3
from datetime import date

from flask import Blueprint, abort, redirect, render_template, request, url_for

from db import get_connection
from kpi import service

kpi_bp = Blueprint("kpi", __name__)


@kpi_bp.route("/team")
def team():
    conn = get_connection()
    members = service.list_members(conn)
    roles = service.list_roles(conn)
    conn.close()
    return render_template("team.html", members=members, roles=roles)


@kpi_bp.route("/dashboard")
def dashboard():
    today = date.today()
    current = str(today.year) + "-Q" + str((today.month - 1) // 3 + 1)
    quarter = request.args.get("quarter", "").strip() or current
    conn = get_connection()
    error = None
    rows = []
    try:
        for member in service.list_members(conn):
            progress = service.kpi_progress(conn, member["id"], quarter)
            rows.append({"member": member, "progress": progress})
    except ValueError:
        error = "Quarter must look like 2026-Q4."
        rows = []
    conn.close()
    return render_template("dashboard.html", quarter=quarter, rows=rows, error=error)


@kpi_bp.route("/roles", methods=["POST"])
def add_role():
    name = request.form.get("name", "").strip()
    conn = get_connection()
    if name:
        try:
            service.create_role(conn, name)
        except sqlite3.IntegrityError:
            pass
    conn.close()
    return redirect(url_for("kpi.team"))


@kpi_bp.route("/members/new", methods=["GET", "POST"])
def add_member():
    conn = get_connection()
    error = None
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        role_id = request.form.get("role_id", "")
        if not name or not email or not role_id:
            error = "Name, email and role are required."
        else:
            try:
                service.create_member(conn, name, email, role_id)
                conn.close()
                return redirect(url_for("kpi.team"))
            except sqlite3.IntegrityError:
                error = "That email is already used or the role does not exist."
    roles = service.list_roles(conn)
    conn.close()
    return render_template("member_form.html", roles=roles, error=error)


@kpi_bp.route("/members/<int:member_id>/targets", methods=["GET", "POST"])
def member_targets(member_id):
    conn = get_connection()
    member = service.get_member(conn, member_id)
    if member is None:
        conn.close()
        abort(404)
    kpis = service.list_kpis(conn, member["role_id"])
    error = None
    if request.method == "POST":
        quarter = request.form.get("quarter", "").strip()
        try:
            for kpi in kpis:
                value = request.form.get("target_" + str(kpi["id"]), "").strip()
                if value:
                    service.set_target(conn, member_id, kpi["id"], quarter, int(value))
            conn.close()
            return redirect(url_for("kpi.member_targets", member_id=member_id))
        except ValueError:
            error = "Quarter must look like 2026-Q4 and targets must be whole numbers."
        except sqlite3.IntegrityError:
            error = "Targets cannot be negative."
    targets = service.list_targets(conn, member_id)
    conn.close()
    return render_template(
        "targets.html",
        member=member,
        kpis=kpis,
        targets=targets,
        metric_keys=service.METRIC_KEYS,
        error=error,
    )


@kpi_bp.route("/members/<int:member_id>/kpis", methods=["POST"])
def add_kpi(member_id):
    conn = get_connection()
    member = service.get_member(conn, member_id)
    if member is None:
        conn.close()
        abort(404)
    name = request.form.get("name", "").strip()
    metric_key = request.form.get("metric_key", "")
    if name:
        try:
            service.create_kpi(conn, member["role_id"], name, metric_key)
        except (ValueError, sqlite3.IntegrityError):
            pass
    conn.close()
    return redirect(url_for("kpi.member_targets", member_id=member_id))

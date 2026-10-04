from datetime import datetime, timezone

from flask import Blueprint, abort, redirect, render_template, request, url_for

from db import get_connection
from kpi.service import active_broker_ids
from routing import service

routing_bp = Blueprint("routing", __name__)


def utc_today():
    # SQLite's CURRENT_TIMESTAMP is UTC, so lead ages are measured against the UTC date
    return datetime.now(timezone.utc).date()


@routing_bp.route("/leads")
def leads():
    conn = get_connection()
    leads = service.list_leads(conn)
    conn.close()
    return render_template("leads.html", leads=leads)


@routing_bp.route("/leads/new", methods=["GET", "POST"])
def add_lead():
    error = None
    if request.method == "POST":
        source = request.form.get("source", "").strip()
        conn = get_connection()
        try:
            if not source:
                raise ValueError
            score = int(request.form.get("score", ""))
            lead_id = service.create_lead(conn, source, score)
            band = service.band_for_score(score)
            broker_ids = active_broker_ids(conn)
            member_id = service.pick_next_broker(conn, band, broker_ids, utc_today())
            if member_id is not None:
                service.assign_lead(conn, lead_id, member_id)
            conn.close()
            return redirect(url_for("routing.leads"))
        except ValueError:
            error = "Source is required and score must be a whole number from 0 to 100."
        conn.close()
    return render_template("lead_form.html", error=error)


@routing_bp.route("/leads/<int:lead_id>/outcome", methods=["GET", "POST"])
def lead_outcome(lead_id):
    conn = get_connection()
    lead = service.get_lead(conn, lead_id)
    if lead is None:
        conn.close()
        abort(404)
    error = None
    if request.method == "POST":
        try:
            service.record_outcome(conn, lead_id, request.form.get("stage", ""))
            conn.close()
            return redirect(url_for("routing.lead_outcome", lead_id=lead_id))
        except ValueError:
            error = "Pick one of the listed stages."
    outcomes = service.list_outcomes(conn, lead_id)
    conn.close()
    return render_template(
        "outcome.html",
        lead=lead,
        band=service.band_for_score(lead["score"]),
        outcomes=outcomes,
        stages=service.STAGES,
        error=error,
    )


@routing_bp.route("/leaderboard")
def leaderboard():
    conn = get_connection()
    today = utc_today()
    brokers = []
    for member_id in active_broker_ids(conn):
        brokers.append({
            "member_id": member_id,
            "score": service.broker_score(conn, member_id, today),
            "open_leads": service.open_lead_count(conn, member_id),
        })
    conn.close()
    brokers.sort(key=lambda broker: broker["score"], reverse=True)
    return render_template("leaderboard.html", brokers=brokers)

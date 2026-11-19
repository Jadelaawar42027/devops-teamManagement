"""Cross-seam integration tests against the running compose stack.

Nothing is stubbed: KPI's GET /dashboard really calls routing's GET /activity over the
Docker network, and routing's POST /leads really calls KPI's GET /brokers/active. The tests
call each service on its own published port, like the browser does (ui/config.js).

    docker compose up -d --build
    KPI_URL=http://localhost:8001 ROUTING_URL=http://localhost:8002 pytest tests/integration

The failure tests need one service stopped first and are switched on by an env var:

    docker compose stop routing && SEAM_ROUTING_STOPPED=1 KPI_URL=... ROUTING_URL=... pytest tests/integration
    docker compose stop kpi     && SEAM_KPI_STOPPED=1     KPI_URL=... ROUTING_URL=... pytest tests/integration

They create their own data (a broker with a unique email, and leads) instead of trusting the
demo seed. The broker is deactivated at the end, so the rotation of real brokers is unchanged.
"""

import os
import uuid
from datetime import datetime, timezone

import pytest
import requests

KPI_URL = os.environ.get("KPI_URL", "").rstrip("/")
ROUTING_URL = os.environ.get("ROUTING_URL", "").rstrip("/")
UI_ORIGIN = os.environ.get("UI_ORIGIN", "http://localhost:8080")
ROUTING_STOPPED = os.environ.get("SEAM_ROUTING_STOPPED") == "1"
KPI_STOPPED = os.environ.get("SEAM_KPI_STOPPED") == "1"
BOTH_UP = not ROUTING_STOPPED and not KPI_STOPPED
TIMEOUT_S = 15

pytestmark = pytest.mark.skipif(
    not (KPI_URL and ROUTING_URL), reason="KPI_URL and ROUTING_URL are not set: needs the compose stack running"
)
needs_both_up = pytest.mark.skipif(not BOTH_UP, reason="one service is stopped on purpose")


def current_quarter():
    today = datetime.now(timezone.utc).date()
    return f"{today.year}-Q{(today.month - 1) // 3 + 1}"


def kpi(method, path, **kwargs):
    return requests.request(method, KPI_URL + path, timeout=TIMEOUT_S, **kwargs)


def routing(method, path, **kwargs):
    return requests.request(method, ROUTING_URL + path, timeout=TIMEOUT_S, **kwargs)


def ok(response, status=200):
    request = f"{response.request.method} {response.url}"
    assert response.status_code == status, f"{request}: {response.status_code} {response.text}"
    return response.json()


def new_lead(score):
    body = {"source": "integration test", "score": score}
    return ok(routing("POST", "/leads", json=body), 201)


def ensure_target(member_id, metric, quarter, value=10):
    """Make sure the member has a KPI on `metric` with a target this quarter; existing targets are kept."""
    kpis = ok(kpi("GET", f"/members/{member_id}/kpis"))["kpis"]
    found = next((k for k in kpis if k["metric"] == metric), None)
    if found is None:
        body = {"name": f"it {metric} {uuid.uuid4().hex[:6]}", "metric": metric}
        found = ok(kpi("POST", f"/members/{member_id}/kpis", json=body), 201)
    year, q = (int(part) for part in quarter.split("-Q"))
    targets = ok(kpi("GET", f"/members/{member_id}/targets"))["targets"]
    if not any(t["kpi_id"] == found["id"] and (t["year"], t["quarter"]) == (year, q) for t in targets):
        body = {"kpi_id": found["id"], "target_value": value, "quarter": quarter}
        ok(kpi("PUT", f"/members/{member_id}/targets", json=body))


def dashboard_actual(member_id, metric, quarter):
    body = ok(kpi("GET", "/dashboard", params={"quarter": quarter}))
    assert body["activity_available"] is True, body["notice"]
    row = next(r for r in body["rows"] if r["member"]["id"] == member_id)
    return next(p["actual"] for p in row["progress"] if p["metric"] == metric)


def is_down(call, path):
    """A stopped container refuses the connection at once: no hang, no partial answer."""
    try:
        call("GET", path)
    except requests.ConnectionError:
        return True
    return False


@pytest.fixture
def fresh_broker():
    """A new active broker: the warm-lead rotation gives the next lead to whoever never had one."""
    roles = ok(kpi("GET", "/roles"))["roles"]
    role = next((r for r in roles if r["name"].lower() == "broker"), None)
    if role is None:
        role = ok(kpi("POST", "/roles", json={"name": "Broker"}), 201)
    email = f"it-{uuid.uuid4().hex[:10]}@example.com"
    body = {"name": "Integration Test", "email": email, "role_id": role["id"]}
    member = ok(kpi("POST", "/members", json=body), 201)
    yield member["id"]
    kpi("POST", f"/members/{member['id']}/deactivate")


@needs_both_up
def test_both_services_are_healthy():
    for call in (kpi, routing):
        body = ok(call("GET", "/health"))
        assert body["status"] == "ok" and body["db"] == "ok" and body["version"]


@needs_both_up
def test_cors_allows_the_ui_origin_only():
    for call in (kpi, routing):
        preflight = call(
            "OPTIONS",
            "/health",
            headers={"Origin": UI_ORIGIN, "Access-Control-Request-Method": "POST"},
        )
        assert preflight.headers.get("Access-Control-Allow-Origin") == UI_ORIGIN
        other = call("GET", "/health", headers={"Origin": "https://not-the-ui.example"})
        assert "Access-Control-Allow-Origin" not in other.headers


@needs_both_up
def test_new_lead_is_assigned_to_a_broker_kpi_reports_as_active(fresh_broker):
    active = ok(kpi("GET", "/brokers/active"))["broker_ids"]
    assert fresh_broker in active
    created = new_lead(50)
    assert created["assignment"] == "assigned"
    assert created["lead"]["assigned_member_id"] in active


@needs_both_up
def test_dashboard_actuals_come_from_routing(fresh_broker):
    quarter = current_quarter()
    for metric in ("leads_assigned", "showings_booked"):
        ensure_target(fresh_broker, metric, quarter)
    assert dashboard_actual(fresh_broker, "leads_assigned", quarter) == 0

    # a warm lead goes to the broker who never had one; retry in case another never-assigned
    # broker (e.g. made by hand in the UI) is ahead in the rotation
    lead = None
    for _ in range(5):
        created = new_lead(50)
        if created["lead"]["assigned_member_id"] == fresh_broker:
            lead = created["lead"]
            break
    assert lead is not None, "the new broker never received a lead"

    # the dashboard (KPI) shows exactly what routing counted for this broker
    activity = ok(routing("GET", "/activity", params={"quarter": quarter, "member_ids": fresh_broker}))
    assert activity["members"][str(fresh_broker)]["leads_assigned"] == 1
    assert dashboard_actual(fresh_broker, "leads_assigned", quarter) == 1

    # an outcome recorded in routing moves the KPI dashboard on the next request
    assert dashboard_actual(fresh_broker, "showings_booked", quarter) == 0
    ok(routing("POST", f"/leads/{lead['id']}/outcomes", json={"stage": "showing_booked"}), 201)
    assert dashboard_actual(fresh_broker, "showings_booked", quarter) == 1


@pytest.mark.skipif(not ROUTING_STOPPED, reason="set SEAM_ROUTING_STOPPED=1 after `docker compose stop routing`")
def test_dashboard_degrades_when_routing_is_stopped():
    assert is_down(routing, "/health")
    body = ok(kpi("GET", "/dashboard", params={"quarter": current_quarter()}))
    assert body["activity_available"] is False
    assert "unavailable" in body["notice"]
    progress = [p for row in body["rows"] for p in row["progress"]]
    assert progress, "expected at least one target on the dashboard"
    assert all(p["target"] is not None and p["actual"] is None and p["percent"] is None for p in progress)
    # KPI keeps serving its own domain, and its health reflects only its own state
    ok(kpi("GET", "/members"))
    assert ok(kpi("GET", "/health"))["status"] == "ok"


@pytest.mark.skipif(not KPI_STOPPED, reason="set SEAM_KPI_STOPPED=1 after `docker compose stop kpi`")
def test_new_lead_is_saved_unassigned_when_kpi_is_stopped():
    assert is_down(kpi, "/health")
    created = new_lead(90)
    assert created["assignment"] == "skipped"
    assert "unavailable" in created["notice"]
    assert created["lead"]["assigned_member_id"] is None
    assert ok(routing("GET", f"/leads/{created['lead']['id']}"))["id"] == created["lead"]["id"]
    leaderboard = ok(routing("GET", "/leaderboard"))
    assert "unavailable" in leaderboard["notice"]
    # routing keeps serving its own domain, and its health reflects only its own state
    assert ok(routing("GET", "/health"))["status"] == "ok"

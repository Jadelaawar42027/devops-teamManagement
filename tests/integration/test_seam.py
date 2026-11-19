"""Cross-seam integration tests against the running compose stack, through the nginx proxy.

Nothing is stubbed: KPI's GET /dashboard really calls routing's GET /activity over the
Docker network, and routing's POST /leads really calls KPI's GET /brokers/active.

    docker compose up -d --build
    STACK_URL=http://localhost:8080 pytest tests/integration

The failure tests need one service stopped first and are switched on by an env var:

    docker compose stop routing && SEAM_ROUTING_STOPPED=1 STACK_URL=... pytest tests/integration
    docker compose stop kpi     && SEAM_KPI_STOPPED=1     STACK_URL=... pytest tests/integration

They create their own data (a broker with a unique email, and leads) instead of trusting the
demo seed. The broker is deactivated at the end, so the rotation of real brokers is unchanged.
"""

import os
import uuid
from datetime import datetime, timezone

import pytest
import requests

STACK_URL = os.environ.get("STACK_URL", "").rstrip("/")
ROUTING_STOPPED = os.environ.get("SEAM_ROUTING_STOPPED") == "1"
KPI_STOPPED = os.environ.get("SEAM_KPI_STOPPED") == "1"
BOTH_UP = not ROUTING_STOPPED and not KPI_STOPPED
TIMEOUT_S = 15

pytestmark = pytest.mark.skipif(not STACK_URL, reason="STACK_URL is not set: needs the compose stack running")
needs_both_up = pytest.mark.skipif(not BOTH_UP, reason="one service is stopped on purpose")


def current_quarter():
    today = datetime.now(timezone.utc).date()
    return f"{today.year}-Q{(today.month - 1) // 3 + 1}"


def call(method, path, **kwargs):
    return requests.request(method, STACK_URL + path, timeout=TIMEOUT_S, **kwargs)


def ok(response, status=200):
    request = f"{response.request.method} {response.url}"
    assert response.status_code == status, f"{request}: {response.status_code} {response.text}"
    return response.json()


def ensure_target(member_id, metric, quarter, value=10):
    """Make sure the member has a KPI on `metric` with a target this quarter; existing targets are kept."""
    kpis = ok(call("GET", f"/api/kpi/members/{member_id}/kpis"))["kpis"]
    kpi = next((k for k in kpis if k["metric"] == metric), None)
    if kpi is None:
        body = {"name": f"it {metric} {uuid.uuid4().hex[:6]}", "metric": metric}
        kpi = ok(call("POST", f"/api/kpi/members/{member_id}/kpis", json=body), 201)
    year, q = (int(part) for part in quarter.split("-Q"))
    targets = ok(call("GET", f"/api/kpi/members/{member_id}/targets"))["targets"]
    if not any(t["kpi_id"] == kpi["id"] and (t["year"], t["quarter"]) == (year, q) for t in targets):
        body = {"kpi_id": kpi["id"], "target_value": value, "quarter": quarter}
        ok(call("PUT", f"/api/kpi/members/{member_id}/targets", json=body))


def dashboard_actual(member_id, metric, quarter):
    body = ok(call("GET", "/api/kpi/dashboard", params={"quarter": quarter}))
    assert body["activity_available"] is True, body["notice"]
    row = next(r for r in body["rows"] if r["member"]["id"] == member_id)
    return next(p["actual"] for p in row["progress"] if p["metric"] == metric)


@pytest.fixture
def fresh_broker():
    """A new active broker: the warm-lead rotation gives the next lead to whoever never had one."""
    roles = ok(call("GET", "/api/kpi/roles"))["roles"]
    role = next((r for r in roles if r["name"].lower() == "broker"), None)
    if role is None:
        role = ok(call("POST", "/api/kpi/roles", json={"name": "Broker"}), 201)
    email = f"it-{uuid.uuid4().hex[:10]}@example.com"
    body = {"name": "Integration Test", "email": email, "role_id": role["id"]}
    member = ok(call("POST", "/api/kpi/members", json=body), 201)
    yield member["id"]
    call("POST", f"/api/kpi/members/{member['id']}/deactivate")


@needs_both_up
def test_proxy_health_needs_both_services():
    assert ok(call("GET", "/health"))["status"] == "ok"
    for service in ("kpi", "routing"):
        assert ok(call("GET", f"/api/{service}/health"))["db"] == "ok"


@needs_both_up
def test_new_lead_is_assigned_to_a_broker_kpi_reports_as_active(fresh_broker):
    active = ok(call("GET", "/api/kpi/brokers/active"))["broker_ids"]
    assert fresh_broker in active
    created = ok(call("POST", "/api/routing/leads", json={"source": "integration test", "score": 50}), 201)
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
        created = ok(call("POST", "/api/routing/leads", json={"source": "integration test", "score": 50}), 201)
        if created["lead"]["assigned_member_id"] == fresh_broker:
            lead = created["lead"]
            break
    assert lead is not None, "the new broker never received a lead"

    # the dashboard (KPI) shows exactly what routing counted for this broker
    activity = ok(call("GET", "/api/routing/activity", params={"quarter": quarter, "member_ids": fresh_broker}))
    assert activity["members"][str(fresh_broker)]["leads_assigned"] == 1
    assert dashboard_actual(fresh_broker, "leads_assigned", quarter) == 1

    # an outcome recorded in routing moves the KPI dashboard on the next request
    assert dashboard_actual(fresh_broker, "showings_booked", quarter) == 0
    ok(call("POST", f"/api/routing/leads/{lead['id']}/outcomes", json={"stage": "showing_booked"}), 201)
    assert dashboard_actual(fresh_broker, "showings_booked", quarter) == 1


@pytest.mark.skipif(not ROUTING_STOPPED, reason="set SEAM_ROUTING_STOPPED=1 after `docker compose stop routing`")
def test_dashboard_degrades_when_routing_is_stopped():
    response = call("GET", "/api/kpi/dashboard", params={"quarter": current_quarter()})
    body = ok(response)
    assert body["activity_available"] is False
    assert "unavailable" in body["notice"]
    progress = [p for row in body["rows"] for p in row["progress"]]
    assert progress, "expected at least one target on the dashboard"
    assert all(p["target"] is not None and p["actual"] is None and p["percent"] is None for p in progress)
    # KPI keeps serving its own domain
    ok(call("GET", "/api/kpi/members"))
    # the proxy answers for the stopped service with JSON, quickly, instead of hanging
    stopped = call("GET", "/api/routing/leads")
    assert stopped.status_code == 503 and stopped.json() == {"error": "Routing service unavailable"}
    assert call("GET", "/health").status_code == 503


@pytest.mark.skipif(not KPI_STOPPED, reason="set SEAM_KPI_STOPPED=1 after `docker compose stop kpi`")
def test_new_lead_is_saved_unassigned_when_kpi_is_stopped():
    created = ok(call("POST", "/api/routing/leads", json={"source": "integration test", "score": 90}), 201)
    assert created["assignment"] == "skipped"
    assert "unavailable" in created["notice"]
    assert created["lead"]["assigned_member_id"] is None
    assert ok(call("GET", f"/api/routing/leads/{created['lead']['id']}"))["id"] == created["lead"]["id"]
    leaderboard = ok(call("GET", "/api/routing/leaderboard"))
    assert "unavailable" in leaderboard["notice"]
    stopped = call("GET", "/api/kpi/members")
    assert stopped.status_code == 503 and stopped.json() == {"error": "KPI service unavailable"}
    assert call("GET", "/health").status_code == 503

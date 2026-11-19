"""The HTTP routes in app.py and web.py, through Flask's test client, on a real database.

Routing is never contacted: every test that reaches GET /dashboard stubs routing's
/activity with `responses`, either answering or failing, so both sides of the seam's
failure handling are tested here without a second service.
"""

import pymssql
import pytest
import requests
import responses
from conftest import MISSING_ID

import app as app_module
import db
import seed
import service

ACTIVITY_URL = "http://routing.test/activity"


@pytest.fixture(autouse=True)
def routing_env(monkeypatch):
    monkeypatch.setenv("ROUTING_URL", "http://routing.test")
    monkeypatch.setenv("ROUTING_TIMEOUT_S", "0.5")


def make_broker_with_target(client, quarter="2026-Q4", metric="deals_closed", target=4):
    role = client.post("/roles", json={"name": "Broker"}).get_json()
    member = client.post("/members", json={"name": "Ana", "email": "ana@example.com", "role_id": role["id"]})
    member_id = member.get_json()["id"]
    kpi = client.post(f"/members/{member_id}/kpis", json={"name": "Deals", "metric": metric}).get_json()
    client.put(f"/members/{member_id}/targets", json={"kpi_id": kpi["id"], "target_value": target, "quarter": quarter})
    return member_id


# --- health, logging, errors ---


def test_health_ok_when_database_is_readable_and_writable(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "db": "ok", "version": "dev"}


def test_health_reports_git_sha(client, monkeypatch):
    monkeypatch.setenv("GIT_SHA", "abc123")
    assert client.get("/health").get_json()["version"] == "abc123"


def test_health_503_when_database_is_unreachable(client, monkeypatch):
    def broken(attempts=None):
        raise pymssql.OperationalError("database not currently available")

    monkeypatch.setattr(db, "get_connection", broken)
    response = client.get("/health")
    assert response.status_code == 503
    assert response.get_json()["db"] == "unavailable"


def test_health_probe_leaves_no_row_behind(client, conn):
    client.get("/health")
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS n FROM schema_migrations WHERE version = '__health_probe__'")
    assert cur.fetchone()["n"] == 0


def test_every_request_is_logged_with_method_path_status_and_duration(client, caplog):
    caplog.set_level("INFO", logger="requests")
    client.get("/roles")
    assert any(r.getMessage().startswith("GET /roles 200 ") and r.getMessage().endswith("ms") for r in caplog.records)


def test_unknown_path_is_json_404(client):
    response = client.get("/nope")
    assert response.status_code == 404
    assert response.get_json() == {"error": "not found"}


def test_wrong_method_is_json_405(client):
    assert client.delete("/roles").status_code == 405


def test_unexpected_error_is_json_500_without_a_stack_trace(client, monkeypatch):
    def boom(conn):
        raise RuntimeError("secret detail")

    monkeypatch.setattr(service, "list_roles", boom)
    response = client.get("/roles")
    assert response.status_code == 500
    assert response.get_json() == {"error": "internal error"}


def test_cors_only_for_the_configured_origin(conn, monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "https://ui.example")
    client = app_module.create_app(migrate=False).test_client()
    allowed = client.get("/roles", headers={"Origin": "https://ui.example"})
    other = client.get("/roles", headers={"Origin": "https://evil.example"})
    assert allowed.headers["Access-Control-Allow-Origin"] == "https://ui.example"
    assert "Access-Control-Allow-Origin" not in other.headers
    assert client.options("/members", headers={"Origin": "https://ui.example"}).status_code == 204


# --- roles and members ---


def test_create_and_list_roles(client):
    response = client.post("/roles", json={"name": " Broker "})
    assert response.status_code == 201
    assert response.get_json()["name"] == "Broker"
    assert [r["name"] for r in client.get("/roles").get_json()["roles"]] == ["Broker"]


def test_role_name_required_and_unique(client):
    assert client.post("/roles", json={}).status_code == 400
    client.post("/roles", json={"name": "Broker"})
    assert client.post("/roles", json={"name": "Broker"}).status_code == 409


def test_create_get_and_list_members(client):
    role_id = client.post("/roles", json={"name": "Broker"}).get_json()["id"]
    created = client.post("/members", json={"name": "Ana", "email": "ana@example.com", "role_id": role_id})
    assert created.status_code == 201
    member = created.get_json()
    assert member["role_name"] == "Broker" and member["active"] == 1
    assert client.get(f"/members/{member['id']}").get_json() == member
    assert client.get("/members").get_json() == {"members": [member]}


@pytest.mark.parametrize(
    "body",
    [
        {"name": "Ana", "email": "ana@example.com", "role_id": "x"},
        {"name": "Ana", "email": "ana@example.com"},
        {"name": "", "email": "ana@example.com", "role_id": 1},
        {"name": "Ana", "email": "not-an-email", "role_id": 1},
    ],
)
def test_create_member_validation(client, body):
    assert client.post("/members", json=body).status_code == 400


def test_create_member_conflicts(client):
    role_id = client.post("/roles", json={"name": "Broker"}).get_json()["id"]
    client.post("/members", json={"name": "Ana", "email": "ana@example.com", "role_id": role_id})
    duplicate_email = {"name": "Other", "email": "ana@example.com", "role_id": role_id}
    assert client.post("/members", json=duplicate_email).status_code == 409
    unknown_role = {"name": "Tom", "email": "tom@example.com", "role_id": MISSING_ID}
    assert client.post("/members", json=unknown_role).status_code == 409


def test_unknown_member_is_404_everywhere(client):
    assert client.get(f"/members/{MISSING_ID}").status_code == 404
    assert client.post(f"/members/{MISSING_ID}/deactivate").status_code == 404
    assert client.get(f"/members/{MISSING_ID}/kpis").status_code == 404
    assert client.post(f"/members/{MISSING_ID}/kpis", json={"name": "x", "metric": "deals_closed"}).status_code == 404
    assert client.get(f"/members/{MISSING_ID}/targets").status_code == 404


def test_deactivate_removes_member_from_active_brokers(client):
    role_id = client.post("/roles", json={"name": "Broker"}).get_json()["id"]
    member_id = client.post("/members", json={"name": "Ana", "email": "a@x.io", "role_id": role_id}).get_json()["id"]
    assert client.get("/brokers/active").get_json() == {"broker_ids": [member_id]}
    response = client.post(f"/members/{member_id}/deactivate")
    assert response.status_code == 200 and response.get_json()["active"] == 0
    assert client.get("/brokers/active").get_json() == {"broker_ids": []}


# --- KPIs and targets ---


def test_kpis_belong_to_the_members_role(client):
    member_id = make_broker_with_target(client)
    kpis = client.get(f"/members/{member_id}/kpis").get_json()["kpis"]
    assert [(k["name"], k["metric"]) for k in kpis] == [("Deals", "deals_closed")]


def test_create_kpi_validation_and_conflict(client):
    member_id = make_broker_with_target(client)
    url = f"/members/{member_id}/kpis"
    assert client.post(url, json={"metric": "deals_closed"}).status_code == 400
    assert client.post(url, json={"name": "Revenue", "metric": "revenue"}).status_code == 400
    assert client.post(url, json={"name": "Deals", "metric": "deals_closed"}).status_code == 409


def test_put_target_upserts_and_returns_all_targets(client):
    member_id = make_broker_with_target(client, target=4)
    kpi_id = client.get(f"/members/{member_id}/kpis").get_json()["kpis"][0]["id"]
    body = {"kpi_id": kpi_id, "target_value": 6, "quarter": "2026-Q4"}
    response = client.put(f"/members/{member_id}/targets", json=body)
    assert response.status_code == 200
    assert [t["target_value"] for t in response.get_json()["targets"]] == [6]
    assert client.get(f"/members/{member_id}/targets").get_json() == response.get_json()


@pytest.mark.parametrize(
    "body",
    [
        {"kpi_id": "x", "target_value": 3, "quarter": "2026-Q4"},
        {"kpi_id": 1, "quarter": "2026-Q4"},
        {"kpi_id": 1, "target_value": 3, "quarter": "2026-4"},
        {"kpi_id": 1, "target_value": -1, "quarter": "2026-Q4"},
    ],
)
def test_put_target_validation(client, body):
    member_id = make_broker_with_target(client)
    assert client.put(f"/members/{member_id}/targets", json=body).status_code == 400


def test_put_target_for_unknown_kpi_or_member_is_409(client):
    member_id = make_broker_with_target(client)
    kpi_id = client.get(f"/members/{member_id}/kpis").get_json()["kpis"][0]["id"]
    body = {"kpi_id": MISSING_ID, "target_value": 3, "quarter": "2026-Q4"}
    assert client.put(f"/members/{member_id}/targets", json=body).status_code == 409
    body = {"kpi_id": kpi_id, "target_value": 3, "quarter": "2026-Q4"}
    assert client.put(f"/members/{MISSING_ID}/targets", json=body).status_code == 409


# --- the dashboard: the flow across the seam ---


@responses.activate
def test_dashboard_combines_targets_with_routing_actuals(client):
    member_id = make_broker_with_target(client, target=4)
    counts = {"leads_assigned": 9, "showings_booked": 5, "showings_performed": 4, "deals_closed": 3}
    responses.get(
        ACTIVITY_URL,
        match=[responses.matchers.query_param_matcher({"quarter": "2026-Q4", "member_ids": str(member_id)})],
        json={"quarter": "2026-Q4", "members": {str(member_id): counts}},
    )
    body = client.get("/dashboard?quarter=2026-Q4").get_json()
    assert body["activity_available"] is True and body["notice"] is None
    assert body["rows"][0]["member"]["id"] == member_id
    assert body["rows"][0]["progress"] == [
        {"kpi_name": "Deals", "metric": "deals_closed", "target": 4, "actual": 3, "percent": 75}
    ]


@responses.activate
@pytest.mark.parametrize(
    "failure",
    [
        {"body": requests.ConnectionError("routing is stopped")},
        {"body": requests.Timeout("routing is too slow")},
        {"status": 503, "json": {"error": "Routing service unavailable"}},
    ],
)
def test_dashboard_degrades_when_routing_is_unavailable(client, failure):
    make_broker_with_target(client, target=4)
    responses.get(ACTIVITY_URL, **failure)
    response = client.get("/dashboard?quarter=2026-Q4")
    assert response.status_code == 200
    body = response.get_json()
    assert body["activity_available"] is False
    assert "unavailable" in body["notice"]
    assert body["rows"][0]["progress"] == [
        {"kpi_name": "Deals", "metric": "deals_closed", "target": 4, "actual": None, "percent": None}
    ]


@responses.activate
def test_dashboard_does_not_call_routing_when_nobody_has_targets(client):
    role_id = client.post("/roles", json={"name": "Broker"}).get_json()["id"]
    client.post("/members", json={"name": "Ana", "email": "ana@example.com", "role_id": role_id})
    body = client.get("/dashboard?quarter=2026-Q4").get_json()
    assert len(responses.calls) == 0
    assert body["rows"][0]["progress"] == []


@responses.activate
def test_dashboard_defaults_to_the_current_quarter(client, monkeypatch):
    monkeypatch.setattr(app_module, "current_quarter", lambda: "2027-Q1")
    assert client.get("/dashboard").get_json()["quarter"] == "2027-Q1"


def test_dashboard_rejects_bad_quarter(client):
    assert client.get("/dashboard?quarter=2026-4").status_code == 400


def test_current_quarter_format():
    year, quarter = app_module.current_quarter().split("-Q")
    assert len(year) == 4 and quarter in {"1", "2", "3", "4"}


# --- startup: migrations and the idempotent demo seed ---


def test_create_app_migrates_and_seeds_once(conn, monkeypatch):
    monkeypatch.setenv("SEED_DEMO", "1")
    app_module.create_app()
    members_after_first_boot = len(service.list_members(conn))
    app_module.create_app()
    assert members_after_first_boot == len(seed.MEMBERS)
    assert len(service.list_members(conn)) == members_after_first_boot
    broker_count = sum(1 for m in seed.MEMBERS if m[2] == "Broker")
    assert len(service.active_broker_ids(conn)) == broker_count

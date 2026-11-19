"""The HTTP routes in app.py and web.py, through Flask's test client, on a real database.

KPI is never contacted: every test that needs the active brokers stubs KPI's
/brokers/active with `responses`, either answering or failing, so both sides of the seam's
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

BROKERS_URL = "http://kpi.test/brokers/active"
KPI_DOWN = [
    {"body": requests.ConnectionError("kpi is stopped")},
    {"body": requests.Timeout("kpi is too slow")},
    {"status": 503, "json": {"error": "KPI service unavailable"}},
]


@pytest.fixture(autouse=True)
def kpi_env(monkeypatch):
    monkeypatch.setenv("KPI_URL", "http://kpi.test")
    monkeypatch.setenv("KPI_TIMEOUT_S", "0.5")


# --- health, logging, errors ---


def test_health_ok_when_database_is_readable_and_writable(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok", "db": "ok", "version": "dev"}


def test_health_503_when_database_is_unreachable(client, monkeypatch):
    def broken(attempts=None):
        raise pymssql.OperationalError("database not currently available")

    monkeypatch.setattr(db, "get_connection", broken)
    response = client.get("/health")
    assert response.status_code == 503
    assert response.get_json() == {"status": "error", "db": "unavailable", "version": "dev"}


@responses.activate
def test_health_does_not_depend_on_kpi(client):
    # health reflects this service's own state only: KPI is not called at all
    assert client.get("/health").status_code == 200
    assert len(responses.calls) == 0


def test_every_request_is_logged_with_method_path_status_and_duration(client, caplog):
    caplog.set_level("INFO", logger="requests")
    client.get("/leads/" + str(MISSING_ID))
    assert any(r.getMessage().startswith(f"GET /leads/{MISSING_ID} 404 ") for r in caplog.records)


def test_unknown_path_is_json_404(client):
    assert client.get("/nope").get_json() == {"error": "not found"}


# --- leads: the flow across the seam (routing asks KPI for the active brokers) ---


@responses.activate
def test_new_lead_is_assigned_to_an_active_broker(client):
    responses.get(BROKERS_URL, json={"broker_ids": [7]})
    response = client.post("/leads", json={"source": "website", "score": 85})
    assert response.status_code == 201
    body = response.get_json()
    assert body["band"] == "hot" and body["assignment"] == "assigned" and body["notice"] is None
    assert body["lead"]["assigned_member_id"] == 7
    assert body["lead"]["assigned_at"].endswith("Z")


@responses.activate
@pytest.mark.parametrize("failure", KPI_DOWN)
def test_new_lead_is_saved_unassigned_when_kpi_is_unavailable(client, failure):
    responses.get(BROKERS_URL, **failure)
    response = client.post("/leads", json={"source": "website", "score": 50})
    assert response.status_code == 201
    body = response.get_json()
    assert body["assignment"] == "skipped"
    assert "unavailable" in body["notice"]
    assert body["lead"]["assigned_member_id"] is None
    # the lead was not lost
    assert client.get(f"/leads/{body['lead']['id']}").status_code == 200


@responses.activate
def test_new_lead_without_active_brokers_is_saved_unassigned(client):
    responses.get(BROKERS_URL, json={"broker_ids": []})
    body = client.post("/leads", json={"source": "website", "score": 50}).get_json()
    assert body["assignment"] == "no_brokers"
    assert body["lead"]["assigned_member_id"] is None


@pytest.mark.parametrize(
    "lead",
    [{"source": "website"}, {"source": "website", "score": "high"}, {"source": "", "score": 50}, {"score": 50}],
)
def test_new_lead_validation(client, lead):
    assert client.post("/leads", json=lead).status_code == 400


def test_new_lead_score_out_of_range_is_400_and_nothing_is_saved(client):
    assert client.post("/leads", json={"source": "website", "score": 101}).status_code == 400
    assert client.get("/leads").get_json() == {"leads": []}


@responses.activate
def test_list_and_get_leads_with_outcomes(client):
    responses.get(BROKERS_URL, json={"broker_ids": [1]})
    lead_id = client.post("/leads", json={"source": "referral", "score": 20}).get_json()["lead"]["id"]
    response = client.post(f"/leads/{lead_id}/outcomes", json={"stage": "showing_booked"})
    assert response.status_code == 201
    assert [o["outcome"] for o in response.get_json()["outcomes"]] == ["showing_booked"]
    listed = client.get("/leads").get_json()["leads"]
    assert [(lead["id"], lead["band"], lead["stage"]) for lead in listed] == [(lead_id, "cold", "showing_booked")]
    detail = client.get(f"/leads/{lead_id}").get_json()
    assert detail["band"] == "cold" and detail["source"] == "referral"
    assert [o["outcome"] for o in detail["outcomes"]] == ["showing_booked"]


def test_outcome_errors(client, conn):
    lead_id = service.create_lead(conn, "website", 50)
    assert client.post(f"/leads/{lead_id}/outcomes", json={"stage": "sold"}).status_code == 400
    assert client.post(f"/leads/{MISSING_ID}/outcomes", json={"stage": "closed"}).status_code == 404
    assert client.get(f"/leads/{MISSING_ID}").status_code == 404


# --- leaderboard ---


@responses.activate
def test_leaderboard_ranks_the_active_brokers(client, conn):
    responses.get(BROKERS_URL, json={"broker_ids": [1, 2]})
    body = client.get("/leaderboard").get_json()
    assert body["notice"] is None
    assert [row["member_id"] for row in body["brokers"]] == [1, 2]


@responses.activate
@pytest.mark.parametrize("failure", KPI_DOWN)
def test_leaderboard_falls_back_to_members_with_leads_when_kpi_is_unavailable(client, conn, failure):
    lead_id = service.create_lead(conn, "website", 50)
    service.assign_lead(conn, lead_id, 5)
    responses.get(BROKERS_URL, **failure)
    body = client.get("/leaderboard").get_json()
    assert "unavailable" in body["notice"]
    assert [row["member_id"] for row in body["brokers"]] == [5]


# --- GET /activity, called by the KPI service ---


def test_activity_returns_counts_for_every_requested_member(client, conn):
    lead_id = service.create_lead(conn, "website", 50)
    service.assign_lead(conn, lead_id, 4)
    quarter = app_module.utc_today()
    quarter = f"{quarter.year}-Q{(quarter.month - 1) // 3 + 1}"
    body = client.get(f"/activity?quarter={quarter}&member_ids=4,9").get_json()
    assert body["quarter"] == quarter
    assert body["members"]["4"]["leads_assigned"] == 1
    assert body["members"]["9"] == {
        "leads_assigned": 0,
        "showings_booked": 0,
        "showings_performed": 0,
        "deals_closed": 0,
    }


def test_activity_without_member_ids_is_empty(client):
    assert client.get("/activity?quarter=2026-Q4").get_json() == {"quarter": "2026-Q4", "members": {}}


@pytest.mark.parametrize(
    "query, message",
    [
        ("member_ids=1", "quarter must look like 2026-Q4"),
        ("quarter=2026-4&member_ids=1", "quarter must look like 2026-Q4"),
        ("quarter=2026-Q4&member_ids=1,x", "member_ids must be comma-separated numbers"),
        ("quarter=2026-Q4&member_ids=" + ",".join(str(i) for i in range(201)), "at most 200 member_ids per call"),
    ],
)
def test_activity_validation(client, query, message):
    response = client.get("/activity?" + query)
    assert response.status_code == 400
    assert response.get_json() == {"error": message}


# --- startup: migrations and the idempotent demo seed ---


@responses.activate
def test_create_app_migrates_and_seeds_once(conn, monkeypatch):
    monkeypatch.setenv("SEED_DEMO", "1")
    responses.get(BROKERS_URL, json={"broker_ids": [1, 2, 3]})
    app_module.create_app()
    app_module.create_app()
    leads = service.list_leads(conn)
    assert len(leads) == seed.LEAD_COUNT
    assert {lead["assigned_member_id"] for lead in leads} == {1, 2, 3}


@responses.activate
def test_seed_is_skipped_while_kpi_is_unavailable(conn, monkeypatch):
    monkeypatch.setattr(seed, "SEED_WAIT_ATTEMPTS", 2)
    monkeypatch.setattr(seed.time, "sleep", lambda s: None)
    responses.get(BROKERS_URL, body=requests.ConnectionError("kpi is stopped"))
    assert seed.seed_demo(conn) is False
    assert service.list_leads(conn) == []


@responses.activate
def test_seed_is_skipped_when_kpi_has_no_brokers_yet(conn, monkeypatch):
    monkeypatch.setattr(seed, "SEED_WAIT_ATTEMPTS", 2)
    monkeypatch.setattr(seed.time, "sleep", lambda s: None)
    responses.get(BROKERS_URL, json={"broker_ids": []})
    assert seed.seed_demo(conn) is False

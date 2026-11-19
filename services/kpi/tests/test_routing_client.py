"""The KPI -> routing call, with routing replaced by `responses` stubs (no network)."""

import pytest
import requests
import responses

import routing_client

ACTIVITY_URL = "http://routing.test/activity"


@pytest.fixture(autouse=True)
def routing_env(monkeypatch):
    monkeypatch.setenv("ROUTING_URL", "http://routing.test/")
    monkeypatch.setenv("ROUTING_TIMEOUT_S", "0.5")


@responses.activate
def test_returns_counts_keyed_by_int_member_id():
    counts = {"leads_assigned": 3, "showings_booked": 1, "showings_performed": 0, "deals_closed": 0}
    responses.get(
        ACTIVITY_URL,
        match=[responses.matchers.query_param_matcher({"quarter": "2026-Q4", "member_ids": "4,7"})],
        json={"quarter": "2026-Q4", "members": {"4": counts, "7": counts}},
    )
    assert routing_client.activity_for_members([4, 7], "2026-Q4") == {4: counts, 7: counts}


@responses.activate
def test_passes_the_configured_timeout():
    responses.get(ACTIVITY_URL, json={"quarter": "2026-Q4", "members": {}})
    routing_client.activity_for_members([1], "2026-Q4")
    assert responses.calls[0].request.req_kwargs["timeout"] == 0.5


@responses.activate
def test_no_members_makes_no_call():
    assert routing_client.activity_for_members([], "2026-Q4") == {}
    assert len(responses.calls) == 0


@responses.activate
@pytest.mark.parametrize("status", [400, 500, 503])
def test_error_status_is_unavailable(status):
    responses.get(ACTIVITY_URL, status=status, json={"error": "x"})
    with pytest.raises(routing_client.RoutingUnavailable):
        routing_client.activity_for_members([1], "2026-Q4")


@responses.activate
@pytest.mark.parametrize("failure", [requests.Timeout("too slow"), requests.ConnectionError("refused")])
def test_timeout_or_connection_error_is_unavailable(failure):
    responses.get(ACTIVITY_URL, body=failure)
    with pytest.raises(routing_client.RoutingUnavailable):
        routing_client.activity_for_members([1], "2026-Q4")

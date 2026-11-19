"""The routing -> KPI call, with KPI replaced by `responses` stubs (no network)."""

import pytest
import requests
import responses

import kpi_client

BROKERS_URL = "http://kpi.test/brokers/active"


@pytest.fixture(autouse=True)
def kpi_env(monkeypatch):
    monkeypatch.setenv("KPI_URL", "http://kpi.test/")
    monkeypatch.setenv("KPI_TIMEOUT_S", "0.5")


@responses.activate
def test_returns_broker_ids():
    responses.get(BROKERS_URL, json={"broker_ids": [1, 3]})
    assert kpi_client.active_broker_ids() == [1, 3]


@responses.activate
def test_passes_the_configured_timeout():
    responses.get(BROKERS_URL, json={"broker_ids": []})
    kpi_client.active_broker_ids()
    assert responses.calls[0].request.req_kwargs["timeout"] == 0.5


@responses.activate
@pytest.mark.parametrize("status", [404, 500, 503])
def test_error_status_is_unavailable(status):
    responses.get(BROKERS_URL, status=status, json={"error": "x"})
    with pytest.raises(kpi_client.KpiUnavailable):
        kpi_client.active_broker_ids()


@responses.activate
@pytest.mark.parametrize("failure", [requests.Timeout("too slow"), requests.ConnectionError("refused")])
def test_timeout_or_connection_error_is_unavailable(failure):
    responses.get(BROKERS_URL, body=failure)
    with pytest.raises(kpi_client.KpiUnavailable):
        kpi_client.active_broker_ids()

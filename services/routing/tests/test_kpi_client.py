import pytest
import requests
import responses

import kpi_client


@pytest.fixture(autouse=True)
def kpi_env(monkeypatch):
    monkeypatch.setenv("KPI_URL", "http://kpi.test")
    monkeypatch.setenv("KPI_TIMEOUT_S", "0.5")


@responses.activate
def test_returns_broker_ids():
    responses.get("http://kpi.test/brokers/active", json={"broker_ids": [1, 3]})
    assert kpi_client.active_broker_ids() == [1, 3]


@responses.activate
def test_error_status_is_unavailable():
    responses.get("http://kpi.test/brokers/active", status=503)
    with pytest.raises(kpi_client.KpiUnavailable):
        kpi_client.active_broker_ids()


@responses.activate
def test_timeout_is_unavailable():
    responses.get("http://kpi.test/brokers/active", body=requests.Timeout("too slow"))
    with pytest.raises(kpi_client.KpiUnavailable):
        kpi_client.active_broker_ids()

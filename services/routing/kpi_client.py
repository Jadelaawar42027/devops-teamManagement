import logging
import os

import requests

log = logging.getLogger(__name__)


class KpiUnavailable(Exception):
    pass


def kpi_url():
    return os.environ.get("KPI_URL", "http://kpi:8000").rstrip("/")


def timeout_s():
    return float(os.environ.get("KPI_TIMEOUT_S", "2"))


def active_broker_ids():
    """GET /brokers/active on the KPI service: ids of members who can receive leads.

    Raises KpiUnavailable on timeout, connection error, or a non-200 answer.
    """
    try:
        response = requests.get(kpi_url() + "/brokers/active", timeout=timeout_s())
    except requests.RequestException as exc:
        log.warning("kpi /brokers/active unreachable: %s", exc)
        raise KpiUnavailable(str(exc)) from exc
    if response.status_code != 200:
        log.warning("kpi /brokers/active answered %s", response.status_code)
        raise KpiUnavailable(f"kpi answered {response.status_code}")
    return [int(i) for i in response.json()["broker_ids"]]

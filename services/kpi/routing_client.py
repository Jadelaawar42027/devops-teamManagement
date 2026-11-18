import logging
import os

import requests

log = logging.getLogger(__name__)


class RoutingUnavailable(Exception):
    pass


def routing_url():
    return os.environ.get("ROUTING_URL", "http://routing:8000").rstrip("/")


def timeout_s():
    return float(os.environ.get("ROUTING_TIMEOUT_S", "2"))


def activity_for_members(member_ids, quarter):
    """GET /activity on the routing service: KPI actuals for many members in one call.

    Returns {member_id: {leads_assigned, showings_booked, showings_performed, deals_closed}}.
    Raises RoutingUnavailable on timeout, connection error, or a non-200 answer.
    """
    if not member_ids:
        return {}
    try:
        response = requests.get(
            routing_url() + "/activity",
            params={"quarter": quarter, "member_ids": ",".join(str(i) for i in member_ids)},
            timeout=timeout_s(),
        )
    except requests.RequestException as exc:
        log.warning("routing /activity unreachable: %s", exc)
        raise RoutingUnavailable(str(exc)) from exc
    if response.status_code != 200:
        log.warning("routing /activity answered %s", response.status_code)
        raise RoutingUnavailable(f"routing answered {response.status_code}")
    members = response.json()["members"]
    return {int(member_id): counts for member_id, counts in members.items()}

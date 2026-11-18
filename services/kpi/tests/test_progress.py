import pytest

from service import kpi_progress, parse_quarter

TARGETS = [
    {"name": "Deals closed", "metric": "deals_closed", "target_value": 4},
    {"name": "Leads assigned", "metric": "leads_assigned", "target_value": 0},
]


def test_progress_with_actuals():
    rows = kpi_progress(TARGETS, {"deals_closed": 3, "leads_assigned": 5})
    assert rows[0] == {"kpi_name": "Deals closed", "metric": "deals_closed", "target": 4, "actual": 3, "percent": 75}
    assert rows[1]["percent"] is None  # target 0: no division by zero


def test_missing_metric_counts_as_zero():
    assert kpi_progress(TARGETS[:1], {})[0]["actual"] == 0


def test_routing_down_keeps_targets_without_actuals():
    rows = kpi_progress(TARGETS, None)
    assert [r["target"] for r in rows] == [4, 0]
    assert all(r["actual"] is None and r["percent"] is None for r in rows)


@pytest.mark.parametrize("bad", ["2026-Q5", "26-Q1", "2026Q1", "2026-Q", ""])
def test_parse_quarter_rejects(bad):
    with pytest.raises(ValueError):
        parse_quarter(bad)


def test_parse_quarter():
    assert parse_quarter("2026-Q4") == (2026, 4)

from datetime import date

import pytest

from routing import service

TODAY = date(2026, 10, 4)


def add_lead(conn, member_id, score, assigned_at, stages=(), created_at="2026-10-04 09:00:00"):
    cur = conn.execute(
        "INSERT INTO leads (source, score, assigned_member_id, assigned_at, created_at) VALUES (?, ?, ?, ?, ?)",
        ("website", score, member_id, assigned_at, created_at),
    )
    conn.commit()
    for stage in stages:
        service.record_outcome(conn, cur.lastrowid, stage)
    return cur.lastrowid


def test_hot_lead_goes_to_highest_scoring_broker(conn):
    add_lead(conn, 1, 80, "2026-10-04 09:00:00")
    add_lead(conn, 2, 80, "2026-10-04 09:00:00", ["closed"])
    assert service.broker_score(conn, 2, TODAY) > service.broker_score(conn, 1, TODAY)
    assert service.pick_next_broker(conn, "hot", [1, 2], TODAY) == 2


def test_hot_lead_ignores_who_was_assigned_most_recently(conn):
    add_lead(conn, 1, 80, "2026-10-01 09:00:00")
    add_lead(conn, 2, 80, "2026-10-04 09:00:00", ["closed"])
    assert service.pick_next_broker(conn, "hot", [1, 2], TODAY) == 2


def test_hot_tie_goes_to_broker_with_fewer_open_leads(conn):
    # a lead older than 90 days no longer affects the score but is still open
    add_lead(conn, 1, 80, "2026-01-01 09:00:00", created_at="2026-01-01 09:00:00")
    assert service.broker_score(conn, 1, TODAY) == service.broker_score(conn, 2, TODAY)
    assert service.pick_next_broker(conn, "hot", [1, 2], TODAY) == 2


def test_warm_lead_goes_to_least_recently_assigned_broker(conn):
    add_lead(conn, 1, 50, "2026-10-03 09:00:00")
    add_lead(conn, 2, 50, "2026-10-01 09:00:00")
    add_lead(conn, 3, 50, "2026-10-02 09:00:00")
    assert service.pick_next_broker(conn, "warm", [1, 2, 3], TODAY) == 2


def test_cold_lead_goes_to_least_recently_assigned_broker(conn):
    add_lead(conn, 1, 20, "2026-10-03 09:00:00")
    add_lead(conn, 2, 20, "2026-10-01 09:00:00")
    assert service.pick_next_broker(conn, "cold", [1, 2], TODAY) == 2


def test_rotation_uses_latest_assignment_not_first(conn):
    add_lead(conn, 1, 50, "2026-09-01 09:00:00")
    add_lead(conn, 1, 50, "2026-10-03 09:00:00")
    add_lead(conn, 2, 50, "2026-10-01 09:00:00")
    assert service.pick_next_broker(conn, "warm", [1, 2], TODAY) == 2


def test_rotation_ignores_score(conn):
    add_lead(conn, 1, 80, "2026-10-03 09:00:00", ["closed"])
    add_lead(conn, 2, 80, "2026-10-01 09:00:00")
    assert service.pick_next_broker(conn, "warm", [1, 2], TODAY) == 2


def test_broker_who_never_got_a_lead_goes_first(conn):
    add_lead(conn, 1, 50, "2026-10-01 09:00:00")
    assert service.pick_next_broker(conn, "warm", [1, 2], TODAY) == 2


def test_rotation_tie_goes_to_broker_with_fewer_open_leads(conn):
    add_lead(conn, 1, 50, "2026-10-01 09:00:00")
    add_lead(conn, 2, 50, "2026-10-01 09:00:00", ["closed"])
    assert service.pick_next_broker(conn, "warm", [1, 2], TODAY) == 2


def test_only_given_brokers_are_considered(conn):
    add_lead(conn, 1, 50, "2026-10-03 09:00:00")
    add_lead(conn, 2, 50, "2026-10-01 09:00:00")
    assert service.pick_next_broker(conn, "warm", [1], TODAY) == 1


def test_no_brokers_returns_none(conn):
    assert service.pick_next_broker(conn, "hot", [], TODAY) is None
    assert service.pick_next_broker(conn, "warm", [], TODAY) is None


def test_open_lead_count_excludes_closed_leads(conn):
    add_lead(conn, 1, 50, "2026-10-01 09:00:00")
    add_lead(conn, 1, 50, "2026-10-01 09:00:00", ["showing_booked"])
    add_lead(conn, 1, 50, "2026-10-01 09:00:00", ["showing_booked", "closed"])
    assert service.open_lead_count(conn, 1) == 2


def test_assign_lead_records_when_it_was_assigned(conn):
    lead_id = service.create_lead(conn, "website", 50)
    assert service.last_assigned_at(conn, 1) is None
    service.assign_lead(conn, lead_id, 1)
    assert service.last_assigned_at(conn, 1) is not None


def add_outcome(conn, lead_id, stage, recorded_at):
    conn.execute(
        "INSERT INTO lead_outcomes (lead_id, outcome, recorded_at) VALUES (?, ?, ?)",
        (lead_id, stage, recorded_at),
    )
    conn.commit()


@pytest.mark.parametrize("score", [-1, 101])
def test_create_lead_rejects_score_outside_0_to_100(conn, score):
    with pytest.raises(ValueError):
        service.create_lead(conn, "website", score)
    assert service.list_leads(conn) == []


@pytest.mark.parametrize("score", [0, 100])
def test_create_lead_accepts_boundary_scores(conn, score):
    lead_id = service.create_lead(conn, "website", score)
    assert service.get_lead(conn, lead_id)["score"] == score


def test_assign_lead_on_missing_lead_raises(conn):
    with pytest.raises(ValueError):
        service.assign_lead(conn, 99, 1)


def test_record_outcome_on_missing_lead_raises(conn):
    with pytest.raises(ValueError):
        service.record_outcome(conn, 99, "closed")


def test_record_outcome_rejects_invalid_stage(conn):
    lead_id = service.create_lead(conn, "website", 50)
    with pytest.raises(ValueError):
        service.record_outcome(conn, lead_id, "sold")
    assert service.list_outcomes(conn, lead_id) == []


def test_quarter_dates():
    assert service.quarter_dates("2026-Q1") == ("2026-01-01", "2026-04-01")
    assert service.quarter_dates("2026-Q3") == ("2026-07-01", "2026-10-01")


def test_quarter_dates_q4_rolls_over_to_next_year():
    assert service.quarter_dates("2026-Q4") == ("2026-10-01", "2027-01-01")


def test_activity_counts_with_no_activity(conn):
    assert service.activity_counts(conn, 1, "2026-Q4") == {
        "leads_assigned": 0,
        "showings_booked": 0,
        "showings_performed": 0,
        "deals_closed": 0,
    }


def test_activity_counts_counts_each_stage(conn):
    first = add_lead(conn, 1, 50, "2026-10-02 09:00:00")
    add_outcome(conn, first, "showing_booked", "2026-10-03 09:00:00")
    add_outcome(conn, first, "showing_performed", "2026-10-05 09:00:00")
    add_outcome(conn, first, "closed", "2026-10-09 09:00:00")
    second = add_lead(conn, 1, 50, "2026-11-02 09:00:00")
    add_outcome(conn, second, "showing_booked", "2026-11-03 09:00:00")
    add_outcome(conn, second, "none", "2026-11-04 09:00:00")
    assert service.activity_counts(conn, 1, "2026-Q4") == {
        "leads_assigned": 2,
        "showings_booked": 2,
        "showings_performed": 1,
        "deals_closed": 1,
    }


def test_activity_counts_outcome_recorded_twice_counts_once(conn):
    lead_id = add_lead(conn, 1, 50, "2026-10-02 09:00:00")
    add_outcome(conn, lead_id, "showing_booked", "2026-10-03 09:00:00")
    add_outcome(conn, lead_id, "showing_booked", "2026-10-04 09:00:00")
    assert service.activity_counts(conn, 1, "2026-Q4")["showings_booked"] == 1


def test_activity_counts_q4_includes_december_and_excludes_january(conn):
    december = add_lead(conn, 1, 50, "2026-12-31 23:59:59")
    add_outcome(conn, december, "closed", "2026-12-31 23:59:59")
    january = add_lead(conn, 1, 50, "2027-01-01 00:00:00")
    add_outcome(conn, january, "closed", "2027-01-01 00:00:00")
    q4 = service.activity_counts(conn, 1, "2026-Q4")
    assert q4["leads_assigned"] == 1
    assert q4["deals_closed"] == 1
    q1 = service.activity_counts(conn, 1, "2027-Q1")
    assert q1["leads_assigned"] == 1
    assert q1["deals_closed"] == 1


def test_activity_counts_excludes_the_previous_quarter(conn):
    lead_id = add_lead(conn, 1, 50, "2026-09-30 23:59:59")
    add_outcome(conn, lead_id, "showing_booked", "2026-09-30 23:59:59")
    counts = service.activity_counts(conn, 1, "2026-Q4")
    assert counts["leads_assigned"] == 0
    assert counts["showings_booked"] == 0


def test_activity_counts_only_counts_the_given_member(conn):
    lead_id = add_lead(conn, 2, 50, "2026-10-02 09:00:00")
    add_outcome(conn, lead_id, "closed", "2026-10-03 09:00:00")
    counts = service.activity_counts(conn, 1, "2026-Q4")
    assert counts["leads_assigned"] == 0
    assert counts["deals_closed"] == 0


def test_get_lead(conn):
    lead_id = service.create_lead(conn, "referral", 72)
    lead = service.get_lead(conn, lead_id)
    assert lead["source"] == "referral"
    assert lead["score"] == 72
    assert lead["assigned_member_id"] is None


def test_get_lead_returns_none_for_unknown_id(conn):
    assert service.get_lead(conn, 99) is None


def test_list_outcomes_in_recorded_order(conn):
    lead_id = service.create_lead(conn, "website", 50)
    service.record_outcome(conn, lead_id, "showing_booked")
    service.record_outcome(conn, lead_id, "showing_performed")
    outcomes = service.list_outcomes(conn, lead_id)
    assert [row["outcome"] for row in outcomes] == ["showing_booked", "showing_performed"]


def test_list_leads_shows_furthest_stage_and_band(conn):
    untouched = add_lead(conn, 1, 20, "2026-10-01 09:00:00")
    went_back = add_lead(conn, 2, 80, "2026-10-01 09:00:00", ["showing_booked", "closed", "showing_booked"])
    leads = service.list_leads(conn)
    assert [lead["id"] for lead in leads] == [went_back, untouched]
    assert leads[0]["stage"] == "closed"
    assert leads[0]["band"] == "hot"
    assert leads[0]["assigned_member_id"] == 2
    assert leads[1]["stage"] == "none"
    assert leads[1]["band"] == "cold"

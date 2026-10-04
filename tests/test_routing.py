from datetime import date

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

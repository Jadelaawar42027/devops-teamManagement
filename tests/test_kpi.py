import pytest

from kpi import service


def add_broker(conn, name="Ana", email="ana@example.com"):
    roles = {role["name"]: role["id"] for role in service.list_roles(conn)}
    if "Broker" not in roles:
        roles["Broker"] = service.create_role(conn, "Broker")
    return service.create_member(conn, name, email, roles["Broker"])


def add_lead(conn, member_id, assigned_at, outcomes=()):
    cur = conn.execute(
        "INSERT INTO leads (source, score, assigned_member_id, assigned_at) VALUES (?, ?, ?, ?)",
        ("website", 50, member_id, assigned_at),
    )
    for stage, recorded_at in outcomes:
        conn.execute(
            "INSERT INTO lead_outcomes (lead_id, outcome, recorded_at) VALUES (?, ?, ?)",
            (cur.lastrowid, stage, recorded_at),
        )
    conn.commit()


def test_create_role_and_list_roles(conn):
    service.create_role(conn, "Setter")
    service.create_role(conn, "Broker")
    assert [role["name"] for role in service.list_roles(conn)] == ["Broker", "Setter"]


def test_create_member_and_list_members_with_role_name(conn):
    role_id = service.create_role(conn, "Broker")
    service.create_member(conn, "Tom", "tom@example.com", role_id)
    service.create_member(conn, "Ana", "ana@example.com", role_id)
    members = service.list_members(conn)
    assert [member["name"] for member in members] == ["Ana", "Tom"]
    assert members[0]["role_name"] == "Broker"
    assert members[0]["active"] == 1


def test_get_member(conn):
    member_id = add_broker(conn)
    member = service.get_member(conn, member_id)
    assert member["name"] == "Ana"
    assert member["email"] == "ana@example.com"
    assert member["role_name"] == "Broker"


def test_get_member_returns_none_for_unknown_id(conn):
    assert service.get_member(conn, 99) is None


def test_active_broker_ids_excludes_inactive_and_non_brokers(conn):
    ana = add_broker(conn, "Ana", "ana@example.com")
    tom = add_broker(conn, "Tom", "tom@example.com")
    inactive = add_broker(conn, "Ines", "ines@example.com")
    conn.execute("UPDATE members SET active = 0 WHERE id = ?", (inactive,))
    conn.commit()
    setter_role = service.create_role(conn, "Setter")
    service.create_member(conn, "Leo", "leo@example.com", setter_role)
    assert service.active_broker_ids(conn) == [ana, tom]


def test_active_broker_ids_is_empty_without_brokers(conn):
    assert service.active_broker_ids(conn) == []


def test_create_kpi_and_list_kpis(conn):
    role_id = service.create_role(conn, "Broker")
    other_role = service.create_role(conn, "Setter")
    service.create_kpi(conn, role_id, "Deals closed", "deals_closed")
    service.create_kpi(conn, other_role, "Bookings", "showings_booked")
    kpis = service.list_kpis(conn, role_id)
    assert len(kpis) == 1
    assert kpis[0]["name"] == "Deals closed"
    assert kpis[0]["metric"] == "deals_closed"


def test_create_kpi_rejects_invalid_metric_key(conn):
    role_id = service.create_role(conn, "Broker")
    with pytest.raises(ValueError):
        service.create_kpi(conn, role_id, "Revenue", "revenue")
    assert service.list_kpis(conn, role_id) == []


def test_parse_quarter_valid():
    assert service.parse_quarter("2026-Q4") == (2026, 4)
    assert service.parse_quarter("2027-Q1") == (2027, 1)


@pytest.mark.parametrize("quarter", ["2026-4", "2026-Q5", "2026-Q0", "26-Q1", "Q4-2026", "", "abcd-Q1"])
def test_parse_quarter_invalid(quarter):
    with pytest.raises(ValueError):
        service.parse_quarter(quarter)


def test_set_target_updates_existing_target(conn):
    member_id = add_broker(conn)
    role_id = service.get_member(conn, member_id)["role_id"]
    kpi_id = service.create_kpi(conn, role_id, "Deals closed", "deals_closed")
    service.set_target(conn, member_id, kpi_id, "2026-Q4", 3)
    service.set_target(conn, member_id, kpi_id, "2026-Q4", 5)
    targets = service.list_targets(conn, member_id)
    assert len(targets) == 1
    assert targets[0]["target_value"] == 5


def test_set_target_rejects_bad_quarter(conn):
    member_id = add_broker(conn)
    role_id = service.get_member(conn, member_id)["role_id"]
    kpi_id = service.create_kpi(conn, role_id, "Deals closed", "deals_closed")
    with pytest.raises(ValueError):
        service.set_target(conn, member_id, kpi_id, "2026-4", 3)
    assert service.list_targets(conn, member_id) == []


def test_list_targets_newest_quarter_first(conn):
    member_id = add_broker(conn)
    role_id = service.get_member(conn, member_id)["role_id"]
    kpi_id = service.create_kpi(conn, role_id, "Deals closed", "deals_closed")
    service.set_target(conn, member_id, kpi_id, "2026-Q3", 2)
    service.set_target(conn, member_id, kpi_id, "2026-Q4", 4)
    targets = service.list_targets(conn, member_id)
    assert [(t["year"], t["quarter"], t["target_value"]) for t in targets] == [(2026, 4, 4), (2026, 3, 2)]
    assert targets[0]["kpi_name"] == "Deals closed"


def test_kpi_progress_compares_actuals_to_targets(conn):
    member_id = add_broker(conn)
    role_id = service.get_member(conn, member_id)["role_id"]
    leads_kpi = service.create_kpi(conn, role_id, "Leads", "leads_assigned")
    service.set_target(conn, member_id, leads_kpi, "2026-Q4", 4)
    add_lead(conn, member_id, "2026-10-02 09:00:00")
    add_lead(conn, member_id, "2026-11-02 09:00:00")
    progress = service.kpi_progress(conn, member_id, "2026-Q4")
    assert progress == [
        {"kpi_name": "Leads", "metric": "leads_assigned", "target": 4, "actual": 2, "percent": 50}
    ]


def test_kpi_progress_zero_target_has_no_percent(conn):
    member_id = add_broker(conn)
    role_id = service.get_member(conn, member_id)["role_id"]
    kpi_id = service.create_kpi(conn, role_id, "Deals closed", "deals_closed")
    service.set_target(conn, member_id, kpi_id, "2026-Q4", 0)
    add_lead(conn, member_id, "2026-10-02 09:00:00", [("closed", "2026-10-05 09:00:00")])
    progress = service.kpi_progress(conn, member_id, "2026-Q4")
    assert progress[0]["actual"] == 1
    assert progress[0]["percent"] is None


def test_kpi_progress_over_achievement_goes_above_100(conn):
    member_id = add_broker(conn)
    role_id = service.get_member(conn, member_id)["role_id"]
    kpi_id = service.create_kpi(conn, role_id, "Deals closed", "deals_closed")
    service.set_target(conn, member_id, kpi_id, "2026-Q4", 2)
    for day in ("05", "06", "07"):
        add_lead(conn, member_id, "2026-10-02 09:00:00", [("closed", "2026-10-" + day + " 09:00:00")])
    progress = service.kpi_progress(conn, member_id, "2026-Q4")
    assert progress[0]["actual"] == 3
    assert progress[0]["percent"] == 150


def test_kpi_progress_no_activity_is_zero_percent(conn):
    member_id = add_broker(conn)
    role_id = service.get_member(conn, member_id)["role_id"]
    kpi_id = service.create_kpi(conn, role_id, "Bookings", "showings_booked")
    service.set_target(conn, member_id, kpi_id, "2026-Q4", 8)
    progress = service.kpi_progress(conn, member_id, "2026-Q4")
    assert progress[0]["actual"] == 0
    assert progress[0]["percent"] == 0


def test_kpi_progress_only_includes_the_requested_quarter(conn):
    member_id = add_broker(conn)
    role_id = service.get_member(conn, member_id)["role_id"]
    kpi_id = service.create_kpi(conn, role_id, "Leads", "leads_assigned")
    service.set_target(conn, member_id, kpi_id, "2026-Q3", 5)
    assert service.kpi_progress(conn, member_id, "2026-Q4") == []


def test_kpi_progress_rejects_bad_quarter(conn):
    member_id = add_broker(conn)
    with pytest.raises(ValueError):
        service.kpi_progress(conn, member_id, "2026-4")

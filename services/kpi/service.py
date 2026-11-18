from db import execute, fetch_all, fetch_one, insert_returning_id

METRIC_KEYS = ["leads_assigned", "showings_booked", "showings_performed", "deals_closed"]


def create_role(conn, name):
    return insert_returning_id(conn, "INSERT INTO roles (name) OUTPUT INSERTED.id VALUES (%s)", (name,))


def list_roles(conn):
    return fetch_all(conn, "SELECT id, name FROM roles ORDER BY name")


def create_member(conn, name, email, role_id):
    return insert_returning_id(
        conn,
        "INSERT INTO members (name, email, role_id) OUTPUT INSERTED.id VALUES (%s, %s, %s)",
        (name, email, role_id),
    )


MEMBER_COLUMNS = """
    members.id, members.name, members.email, CAST(members.active AS INT) AS active,
    members.role_id, roles.name AS role_name
"""


def list_members(conn):
    return fetch_all(
        conn,
        f"SELECT {MEMBER_COLUMNS} FROM members JOIN roles ON roles.id = members.role_id ORDER BY members.name",
    )


def get_member(conn, member_id):
    return fetch_one(
        conn,
        f"SELECT {MEMBER_COLUMNS} FROM members JOIN roles ON roles.id = members.role_id WHERE members.id = %s",
        (member_id,),
    )


def active_broker_ids(conn):
    rows = fetch_all(
        conn,
        """
        SELECT members.id
        FROM members
        JOIN roles ON roles.id = members.role_id
        WHERE members.active = 1 AND LOWER(roles.name) = 'broker'
        ORDER BY members.id
        """,
    )
    return [row["id"] for row in rows]


def list_kpis(conn, role_id):
    return fetch_all(
        conn,
        "SELECT id, name, metric, description FROM kpi_definitions WHERE role_id = %s ORDER BY name",
        (role_id,),
    )


def create_kpi(conn, role_id, name, metric_key, description=None):
    if metric_key not in METRIC_KEYS:
        raise ValueError("metric_key must be one of: " + ", ".join(METRIC_KEYS))
    return insert_returning_id(
        conn,
        "INSERT INTO kpi_definitions (role_id, name, metric, description) OUTPUT INSERTED.id VALUES (%s, %s, %s, %s)",
        (role_id, name, metric_key, description),
    )


def list_targets(conn, member_id):
    return fetch_all(
        conn,
        """
        SELECT kpi_definitions.id AS kpi_id, kpi_definitions.name AS kpi_name, kpi_targets.year,
               kpi_targets.quarter, kpi_targets.target_value
        FROM kpi_targets
        JOIN kpi_definitions ON kpi_definitions.id = kpi_targets.kpi_id
        WHERE kpi_targets.member_id = %s
        ORDER BY kpi_targets.year DESC, kpi_targets.quarter DESC, kpi_definitions.name
        """,
        (member_id,),
    )


def parse_quarter(quarter):
    parts = quarter.split("-Q")
    if len(parts) != 2 or len(parts[0]) != 4 or not parts[0].isdigit() or parts[1] not in ("1", "2", "3", "4"):
        raise ValueError("quarter must look like 2026-Q4")
    return int(parts[0]), int(parts[1])


def set_target(conn, member_id, kpi_id, quarter, target_value):
    year, q = parse_quarter(quarter)
    if target_value < 0:
        raise ValueError("target must be 0 or more")
    # SQL Server has no ON CONFLICT: update first, insert if nothing was updated
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE kpi_targets SET target_value = %s
        WHERE kpi_id = %s AND member_id = %s AND year = %s AND quarter = %s
        """,
        (target_value, kpi_id, member_id, year, q),
    )
    if cur.rowcount == 0:
        cur.execute(
            "INSERT INTO kpi_targets (kpi_id, member_id, year, quarter, target_value) VALUES (%s, %s, %s, %s, %s)",
            (kpi_id, member_id, year, q, target_value),
        )
    conn.commit()


def member_targets_for_quarter(conn, member_id, quarter):
    year, q = parse_quarter(quarter)
    return fetch_all(
        conn,
        """
        SELECT kpi_definitions.name, kpi_definitions.metric, kpi_targets.target_value
        FROM kpi_targets
        JOIN kpi_definitions ON kpi_definitions.id = kpi_targets.kpi_id
        WHERE kpi_targets.member_id = %s AND kpi_targets.year = %s AND kpi_targets.quarter = %s
        ORDER BY kpi_definitions.name
        """,
        (member_id, year, q),
    )


def kpi_progress(targets, counts):
    """Compare targets with the routing service's activity counts.

    counts is the dict routing returns for one member, or None when routing could not be
    reached: targets are still shown, with actual and percent set to None (ADR-6).
    """
    progress = []
    for row in targets:
        target = row["target_value"]
        actual = None if counts is None else counts.get(row["metric"], 0)
        percent = None
        if actual is not None and target > 0:
            percent = round(actual / target * 100)
        progress.append(
            {
                "kpi_name": row["name"],
                "metric": row["metric"],
                "target": target,
                "actual": actual,
                "percent": percent,
            }
        )
    return progress


def deactivate_member(conn, member_id):
    # members are never deleted: routing keeps their id on leads with no foreign key (ADR-3)
    if execute(conn, "UPDATE members SET active = 0 WHERE id = %s", (member_id,)) == 0:
        raise ValueError("member not found")

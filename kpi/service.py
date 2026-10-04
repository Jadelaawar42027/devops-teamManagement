from routing.service import activity_counts

METRIC_KEYS = ["leads_assigned", "showings_booked", "showings_performed", "deals_closed"]


def create_role(conn, name):
    cur = conn.execute("INSERT INTO roles (name) VALUES (?)", (name,))
    conn.commit()
    return cur.lastrowid


def list_roles(conn):
    return conn.execute("SELECT id, name FROM roles ORDER BY name").fetchall()


def create_member(conn, name, email, role_id):
    cur = conn.execute(
        "INSERT INTO members (name, email, role_id) VALUES (?, ?, ?)",
        (name, email, role_id),
    )
    conn.commit()
    return cur.lastrowid


def list_members(conn):
    return conn.execute(
        """
        SELECT members.id, members.name, members.email, members.active,
               members.role_id, roles.name AS role_name
        FROM members
        JOIN roles ON roles.id = members.role_id
        ORDER BY members.name
        """
    ).fetchall()


def active_broker_ids(conn):
    rows = conn.execute(
        """
        SELECT members.id
        FROM members
        JOIN roles ON roles.id = members.role_id
        WHERE members.active = 1 AND LOWER(roles.name) = 'broker'
        ORDER BY members.id
        """
    ).fetchall()
    return [row["id"] for row in rows]


def get_member(conn, member_id):
    return conn.execute(
        """
        SELECT members.id, members.name, members.email, members.role_id,
               roles.name AS role_name
        FROM members
        JOIN roles ON roles.id = members.role_id
        WHERE members.id = ?
        """,
        (member_id,),
    ).fetchone()


def list_kpis(conn, role_id):
    return conn.execute(
        "SELECT id, name, metric FROM kpi_definitions WHERE role_id = ? ORDER BY name",
        (role_id,),
    ).fetchall()


def list_targets(conn, member_id):
    return conn.execute(
        """
        SELECT kpi_definitions.name AS kpi_name, kpi_targets.year,
               kpi_targets.quarter, kpi_targets.target_value
        FROM kpi_targets
        JOIN kpi_definitions ON kpi_definitions.id = kpi_targets.kpi_id
        WHERE kpi_targets.member_id = ?
        ORDER BY kpi_targets.year DESC, kpi_targets.quarter DESC, kpi_definitions.name
        """,
        (member_id,),
    ).fetchall()


def create_kpi(conn, role_id, name, metric_key, description=None):
    if metric_key not in METRIC_KEYS:
        raise ValueError("metric_key must be one of: " + ", ".join(METRIC_KEYS))
    cur = conn.execute(
        "INSERT INTO kpi_definitions (role_id, name, metric, description) VALUES (?, ?, ?, ?)",
        (role_id, name, metric_key, description),
    )
    conn.commit()
    return cur.lastrowid


def parse_quarter(quarter):
    parts = quarter.split("-Q")
    if len(parts) != 2 or len(parts[0]) != 4 or not parts[0].isdigit() or parts[1] not in ("1", "2", "3", "4"):
        raise ValueError("quarter must look like 2026-Q4")
    return int(parts[0]), int(parts[1])


def set_target(conn, member_id, kpi_id, quarter, target_value):
    year, q = parse_quarter(quarter)
    conn.execute(
        """
        INSERT INTO kpi_targets (kpi_id, member_id, year, quarter, target_value)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (kpi_id, member_id, year, quarter)
        DO UPDATE SET target_value = excluded.target_value
        """,
        (kpi_id, member_id, year, q, target_value),
    )
    conn.commit()


def kpi_progress(conn, member_id, quarter):
    year, q = parse_quarter(quarter)
    targets = conn.execute(
        """
        SELECT kpi_definitions.name, kpi_definitions.metric, kpi_targets.target_value
        FROM kpi_targets
        JOIN kpi_definitions ON kpi_definitions.id = kpi_targets.kpi_id
        WHERE kpi_targets.member_id = ? AND kpi_targets.year = ? AND kpi_targets.quarter = ?
        ORDER BY kpi_definitions.name
        """,
        (member_id, year, q),
    ).fetchall()
    counts = activity_counts(conn, member_id, quarter)
    progress = []
    for row in targets:
        target = row["target_value"]
        actual = counts[row["metric"]]
        percent = None
        if target > 0:
            percent = round(actual / target * 100)
        progress.append({
            "kpi_name": row["name"],
            "metric": row["metric"],
            "target": target,
            "actual": actual,
            "percent": percent,
        })
    return progress

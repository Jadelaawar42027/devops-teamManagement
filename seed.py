from datetime import datetime, timedelta, timezone

from db import get_connection
from kpi import service as kpi_service

QUARTER = "2026-Q4"
ROLES = ["Broker", "Setter", "Sales Manager", "Marketing"]
MEMBERS = [
    ("Marta Ruiz", "marta@example.com", "Broker"),
    ("Tom Becker", "tom@example.com", "Broker"),
    ("Ines Costa", "ines@example.com", "Broker"),
    ("Leo Marsh", "leo@example.com", "Setter"),
    ("Dana Holt", "dana@example.com", "Sales Manager"),
    ("Sam Okoye", "sam@example.com", "Marketing"),
]
BROKER_KPIS = [
    ("Leads assigned", "leads_assigned", 15),
    ("Showings booked", "showings_booked", 8),
    ("Showings performed", "showings_performed", 5),
    ("Deals closed", "deals_closed", 2),
]
SOURCES = ["website", "referral", "boat show", "phone"]
LEAD_COUNT = 30
AGES_IN_DAYS = [0, 1, 2, 3, 4, 6, 9, 14, 25, 40]
# how many stages each lead gets through: 0 = no outcome yet, 3 = closed
STAGES_REACHED = [3, 1, 2, 0, 3, 2, 1]
STAGE_DELAYS = [("showing_booked", 1), ("showing_performed", 2), ("closed", 4)]


def seed_demo():
    conn = get_connection()
    if conn.execute("SELECT COUNT(*) FROM members").fetchone()[0] > 0:
        conn.close()
        return

    role_ids = {}
    for name in ROLES:
        role_ids[name] = kpi_service.create_role(conn, name)

    broker_ids = []
    for name, email, role in MEMBERS:
        member_id = kpi_service.create_member(conn, name, email, role_ids[role])
        if role == "Broker":
            broker_ids.append(member_id)

    for name, metric_key, target in BROKER_KPIS:
        kpi_id = kpi_service.create_kpi(conn, role_ids["Broker"], name, metric_key)
        for member_id in broker_ids:
            kpi_service.set_target(conn, member_id, kpi_id, QUARTER, target)

    now = datetime.now(timezone.utc)
    for i in range(LEAD_COUNT):
        created = now - timedelta(days=AGES_IN_DAYS[i % len(AGES_IN_DAYS)], hours=i % 8)
        created_text = created.strftime("%Y-%m-%d %H:%M:%S")
        cur = conn.execute(
            """
            INSERT INTO leads (source, score, assigned_member_id, assigned_at, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                SOURCES[i % len(SOURCES)],
                (i * 37 + 11) % 101,
                broker_ids[i % len(broker_ids)],
                created_text,
                created_text,
            ),
        )
        reached = STAGES_REACHED[i % len(STAGES_REACHED)]
        for stage, delay in STAGE_DELAYS[:reached]:
            recorded = created + timedelta(days=delay)
            # a recent lead has not had time to reach its later stages yet
            if recorded <= now:
                conn.execute(
                    "INSERT INTO lead_outcomes (lead_id, outcome, recorded_at) VALUES (?, ?, ?)",
                    (cur.lastrowid, stage, recorded.strftime("%Y-%m-%d %H:%M:%S")),
                )
    conn.commit()
    conn.close()

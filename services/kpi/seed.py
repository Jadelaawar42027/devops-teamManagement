import logging
from datetime import datetime, timezone

import service

log = logging.getLogger(__name__)

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


def seed_demo(conn):
    """Idempotent: does nothing once any member exists, so it is safe on every start."""
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS n FROM members")
    if cur.fetchone()["n"] > 0:
        return False
    today = datetime.now(timezone.utc).date()
    quarter = f"{today.year}-Q{(today.month - 1) // 3 + 1}"

    role_ids = {name: service.create_role(conn, name) for name in ROLES}
    broker_ids = []
    for name, email, role in MEMBERS:
        member_id = service.create_member(conn, name, email, role_ids[role])
        if role == "Broker":
            broker_ids.append(member_id)
    for name, metric_key, target in BROKER_KPIS:
        kpi_id = service.create_kpi(conn, role_ids["Broker"], name, metric_key)
        for member_id in broker_ids:
            service.set_target(conn, member_id, kpi_id, quarter, target)
    log.info("seeded demo data: %d members, targets for %s", len(MEMBERS), quarter)
    return True

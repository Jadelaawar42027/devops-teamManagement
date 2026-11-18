import logging
import time
from datetime import datetime, timedelta, timezone

import kpi_client

log = logging.getLogger(__name__)

SOURCES = ["website", "referral", "boat show", "phone"]
LEAD_COUNT = 30
AGES_IN_DAYS = [0, 1, 2, 3, 4, 6, 9, 14, 25, 40]
# how many stages each lead gets through: 0 = no outcome yet, 3 = closed
STAGES_REACHED = [3, 1, 2, 0, 3, 2, 1]
STAGE_DELAYS = [("showing_booked", 1), ("showing_performed", 2), ("closed", 4)]
SEED_WAIT_ATTEMPTS = 20
SEED_WAIT_S = 3


def seed_demo(conn):
    """Idempotent: does nothing once any lead exists.

    Leads are assigned to the KPI service's brokers, fetched over HTTP. If KPI is not up yet,
    seeding is skipped and tried again on the next start.
    """
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) AS n FROM leads")
    if cur.fetchone()["n"] > 0:
        return False
    broker_ids = None
    # kpi usually starts at the same time and seeds its brokers first, so wait for it a little
    for _ in range(SEED_WAIT_ATTEMPTS):
        try:
            broker_ids = kpi_client.active_broker_ids()
            if broker_ids:
                break
        except kpi_client.KpiUnavailable:
            pass
        time.sleep(SEED_WAIT_S)
    if broker_ids is None:
        log.warning("demo seed skipped: kpi service unavailable, will retry on next start")
        return False
    if not broker_ids:
        log.warning("demo seed skipped: kpi service has no active brokers yet")
        return False

    now = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
    for i in range(LEAD_COUNT):
        created = now - timedelta(days=AGES_IN_DAYS[i % len(AGES_IN_DAYS)], hours=i % 8)
        cur.execute(
            """
            INSERT INTO leads (source, score, assigned_member_id, assigned_at, created_at)
            OUTPUT INSERTED.id
            VALUES (%s, %s, %s, %s, %s)
            """,
            (SOURCES[i % len(SOURCES)], (i * 37 + 11) % 101, broker_ids[i % len(broker_ids)], created, created),
        )
        lead_id = cur.fetchone()["id"]
        for stage, delay in STAGE_DELAYS[: STAGES_REACHED[i % len(STAGES_REACHED)]]:
            recorded = created + timedelta(days=delay)
            # a recent lead has not had time to reach its later stages yet
            if recorded <= now:
                cur.execute(
                    "INSERT INTO lead_outcomes (lead_id, outcome, recorded_at) VALUES (%s, %s, %s)",
                    (lead_id, stage, recorded),
                )
    conn.commit()
    log.info("seeded demo data: %d leads", LEAD_COUNT)
    return True

from datetime import date, datetime, timedelta

from db import fetch_all, fetch_one, insert_returning_id

STAGES = ["none", "showing_booked", "showing_performed", "closed"]
OUTCOME_POINTS = {"none": 0, "showing_booked": 1, "showing_performed": 2, "closed": 4}
EXPECTED_POINTS = {"hot": 2.5, "warm": 1.5, "cold": 0.5}
SCORE_WINDOW_DAYS = 90
HALF_LIFE_DAYS = 30
STAGE_METRICS = {
    "showing_booked": "showings_booked",
    "showing_performed": "showings_performed",
    "closed": "deals_closed",
}
EMPTY_COUNTS = {"leads_assigned": 0, "showings_booked": 0, "showings_performed": 0, "deals_closed": 0}


def band_for_score(score):
    if score >= 70:
        return "hot"
    if score >= 40:
        return "warm"
    return "cold"


def create_lead(conn, source, score):
    if score < 0 or score > 100:
        raise ValueError("score must be between 0 and 100")
    return insert_returning_id(
        conn,
        "INSERT INTO leads (source, score) OUTPUT INSERTED.id VALUES (%s, %s)",
        (source, score),
    )


def assign_lead(conn, lead_id, member_id):
    cur = conn.cursor()
    cur.execute(
        "UPDATE leads SET assigned_member_id = %s, assigned_at = SYSUTCDATETIME() WHERE id = %s",
        (member_id, lead_id),
    )
    conn.commit()
    if cur.rowcount == 0:
        raise ValueError("lead not found")


def record_outcome(conn, lead_id, stage):
    if stage not in STAGES:
        raise ValueError("stage must be one of: " + ", ".join(STAGES))
    if fetch_one(conn, "SELECT id FROM leads WHERE id = %s", (lead_id,)) is None:
        raise LookupError("lead not found")
    return insert_returning_id(
        conn,
        "INSERT INTO lead_outcomes (lead_id, outcome) OUTPUT INSERTED.id VALUES (%s, %s)",
        (lead_id, stage),
    )


def score_from_results(results):
    total = 0
    for points, band, age_days in results:
        weight = 0.5 ** (age_days / HALF_LIFE_DAYS)
        total += (points - EXPECTED_POINTS[band]) * weight
    return total


def broker_score(conn, member_id, today):
    cutoff = today - timedelta(days=SCORE_WINDOW_DAYS)
    rows = fetch_all(
        conn,
        """
        SELECT leads.id, leads.score, leads.created_at, lead_outcomes.outcome
        FROM leads
        LEFT JOIN lead_outcomes ON lead_outcomes.lead_id = leads.id
        WHERE leads.assigned_member_id = %s
          AND CAST(leads.created_at AS DATE) BETWEEN %s AND %s
        """,
        (member_id, cutoff, today),
    )
    # one row per outcome, so keep only the furthest outcome for each lead
    results = {}
    for row in rows:
        points = OUTCOME_POINTS.get(row["outcome"], 0)
        if row["id"] not in results or points > results[row["id"]][0]:
            age_days = (today - row["created_at"].date()).days
            results[row["id"]] = (points, band_for_score(row["score"]), age_days)
    return score_from_results(list(results.values()))


def open_lead_count(conn, member_id):
    return fetch_one(
        conn,
        """
        SELECT COUNT(*) AS n FROM leads
        WHERE assigned_member_id = %s
          AND id NOT IN (SELECT lead_id FROM lead_outcomes WHERE outcome = 'closed')
        """,
        (member_id,),
    )["n"]


def last_assigned_at(conn, member_id):
    return fetch_one(
        conn, "SELECT MAX(assigned_at) AS last FROM leads WHERE assigned_member_id = %s", (member_id,)
    )["last"]


def pick_next_broker(conn, band, broker_ids, today):
    if not broker_ids:
        return None

    # min() picks the smallest tuple, so each rule is one position in it
    def rank(member_id):
        open_leads = open_lead_count(conn, member_id)
        if band == "hot":
            return (-broker_score(conn, member_id, today), open_leads, member_id)
        # a broker who never got a lead sorts before any timestamp (datetime.min, not "",
        # because SQL Server returns datetimes, and a str cannot be compared with one)
        return (last_assigned_at(conn, member_id) or datetime.min, open_leads, member_id)

    return min(broker_ids, key=rank)


def quarter_dates(quarter):
    parts = quarter.split("-Q")
    if len(parts) != 2 or len(parts[0]) != 4 or not parts[0].isdigit() or parts[1] not in ("1", "2", "3", "4"):
        raise ValueError("quarter must look like 2026-Q4")
    year, q = int(parts[0]), int(parts[1])
    start = date(year, 3 * q - 2, 1)
    end = date(year + 1, 1, 1) if q == 4 else date(year, 3 * q + 1, 1)
    return start, end


def activity_counts_bulk(conn, member_ids, quarter):
    """KPI actuals for many members at once; replaces ADR-2's one-call-per-member activity_counts()."""
    start, end = quarter_dates(quarter)
    counts = {member_id: dict(EMPTY_COUNTS) for member_id in member_ids}
    if not member_ids:
        return counts
    placeholders = ", ".join(["%s"] * len(member_ids))
    for row in fetch_all(
        conn,
        f"""
        SELECT assigned_member_id AS member_id, COUNT(*) AS total FROM leads
        WHERE assigned_member_id IN ({placeholders}) AND assigned_at >= %s AND assigned_at < %s
        GROUP BY assigned_member_id
        """,
        (*member_ids, start, end),
    ):
        counts[row["member_id"]]["leads_assigned"] = row["total"]
    # DISTINCT so an outcome recorded twice for the same lead counts once
    for row in fetch_all(
        conn,
        f"""
        SELECT leads.assigned_member_id AS member_id, lead_outcomes.outcome,
               COUNT(DISTINCT leads.id) AS total
        FROM lead_outcomes
        JOIN leads ON leads.id = lead_outcomes.lead_id
        WHERE leads.assigned_member_id IN ({placeholders})
          AND lead_outcomes.recorded_at >= %s AND lead_outcomes.recorded_at < %s
        GROUP BY leads.assigned_member_id, lead_outcomes.outcome
        """,
        (*member_ids, start, end),
    ):
        if row["outcome"] in STAGE_METRICS:
            counts[row["member_id"]][STAGE_METRICS[row["outcome"]]] = row["total"]
    return counts


LEAD_COLUMNS = "id, source, score, assigned_member_id, assigned_at, created_at"


def get_lead(conn, lead_id):
    return fetch_one(conn, f"SELECT {LEAD_COLUMNS} FROM leads WHERE id = %s", (lead_id,))


def list_outcomes(conn, lead_id):
    return fetch_all(
        conn, "SELECT outcome, recorded_at FROM lead_outcomes WHERE lead_id = %s ORDER BY id", (lead_id,)
    )


def furthest_stages(conn):
    furthest = {}
    for row in fetch_all(conn, "SELECT lead_id, outcome FROM lead_outcomes"):
        current = furthest.get(row["lead_id"], "none")
        if OUTCOME_POINTS[row["outcome"]] > OUTCOME_POINTS[current]:
            furthest[row["lead_id"]] = row["outcome"]
    return furthest


def list_leads(conn):
    furthest = furthest_stages(conn)
    leads = []
    for row in fetch_all(conn, f"SELECT {LEAD_COLUMNS} FROM leads ORDER BY id DESC"):
        lead = dict(row)
        lead["band"] = band_for_score(row["score"])
        lead["stage"] = furthest.get(row["id"], "none")
        leads.append(lead)
    return leads


def assigned_member_ids(conn):
    rows = fetch_all(conn, "SELECT DISTINCT assigned_member_id AS id FROM leads WHERE assigned_member_id IS NOT NULL")
    return sorted(row["id"] for row in rows)


def leaderboard(conn, broker_ids, today):
    rows = [
        {
            "member_id": member_id,
            "score": round(broker_score(conn, member_id, today), 2),
            "open_leads": open_lead_count(conn, member_id),
        }
        for member_id in broker_ids
    ]
    return sorted(rows, key=lambda r: (-r["score"], r["open_leads"], r["member_id"]))

from datetime import date, timedelta

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


def band_for_score(score):
    if score >= 70:
        return "hot"
    if score >= 40:
        return "warm"
    return "cold"


def create_lead(conn, source, score):
    if score < 0 or score > 100:
        raise ValueError("score must be between 0 and 100")
    cur = conn.execute(
        "INSERT INTO leads (source, score) VALUES (?, ?)",
        (source, score),
    )
    conn.commit()
    return cur.lastrowid


def assign_lead(conn, lead_id, member_id):
    cur = conn.execute(
        "UPDATE leads SET assigned_member_id = ?, assigned_at = CURRENT_TIMESTAMP WHERE id = ?",
        (member_id, lead_id),
    )
    conn.commit()
    if cur.rowcount == 0:
        raise ValueError("lead not found")


def record_outcome(conn, lead_id, stage):
    if stage not in STAGES:
        raise ValueError("stage must be one of: " + ", ".join(STAGES))
    lead = conn.execute("SELECT id FROM leads WHERE id = ?", (lead_id,)).fetchone()
    if lead is None:
        raise ValueError("lead not found")
    cur = conn.execute(
        "INSERT INTO lead_outcomes (lead_id, outcome) VALUES (?, ?)",
        (lead_id, stage),
    )
    conn.commit()
    return cur.lastrowid


def score_from_results(results):
    total = 0
    for points, band, age_days in results:
        weight = 0.5 ** (age_days / HALF_LIFE_DAYS)
        total += (points - EXPECTED_POINTS[band]) * weight
    return total


def broker_score(conn, member_id, today):
    cutoff = today - timedelta(days=SCORE_WINDOW_DAYS)
    rows = conn.execute(
        """
        SELECT leads.id, leads.score, leads.created_at, lead_outcomes.outcome
        FROM leads
        LEFT JOIN lead_outcomes ON lead_outcomes.lead_id = leads.id
        WHERE leads.assigned_member_id = ?
          AND date(leads.created_at) BETWEEN ? AND ?
        """,
        (member_id, cutoff.isoformat(), today.isoformat()),
    ).fetchall()
    # one row per outcome, so keep only the furthest outcome for each lead
    results = {}
    for row in rows:
        points = OUTCOME_POINTS.get(row["outcome"], 0)
        if row["id"] not in results or points > results[row["id"]][0]:
            age_days = (today - date.fromisoformat(row["created_at"][:10])).days
            results[row["id"]] = (points, band_for_score(row["score"]), age_days)
    return score_from_results(list(results.values()))


def open_lead_count(conn, member_id):
    return conn.execute(
        """
        SELECT COUNT(*) FROM leads
        WHERE assigned_member_id = ?
          AND id NOT IN (SELECT lead_id FROM lead_outcomes WHERE outcome = 'closed')
        """,
        (member_id,),
    ).fetchone()[0]


def last_assigned_at(conn, member_id):
    return conn.execute(
        "SELECT MAX(assigned_at) FROM leads WHERE assigned_member_id = ?",
        (member_id,),
    ).fetchone()[0]


def pick_next_broker(conn, band, broker_ids, today):
    if not broker_ids:
        return None

    # min() picks the smallest tuple, so each rule is one position in it
    def rank(member_id):
        open_leads = open_lead_count(conn, member_id)
        if band == "hot":
            return (-broker_score(conn, member_id, today), open_leads, member_id)
        # a broker who never got a lead sorts before any timestamp
        return (last_assigned_at(conn, member_id) or "", open_leads, member_id)

    return min(broker_ids, key=rank)


def quarter_dates(quarter):
    year, q = quarter.split("-Q")
    year, q = int(year), int(q)
    start = date(year, 3 * q - 2, 1)
    if q == 4:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, 3 * q + 1, 1)
    return start.isoformat(), end.isoformat()


def activity_counts(conn, member_id, quarter):
    start, end = quarter_dates(quarter)
    counts = {
        "leads_assigned": 0,
        "showings_booked": 0,
        "showings_performed": 0,
        "deals_closed": 0,
    }
    counts["leads_assigned"] = conn.execute(
        """
        SELECT COUNT(*) FROM leads
        WHERE assigned_member_id = ? AND assigned_at >= ? AND assigned_at < ?
        """,
        (member_id, start, end),
    ).fetchone()[0]
    # DISTINCT so an outcome recorded twice for the same lead counts once
    rows = conn.execute(
        """
        SELECT lead_outcomes.outcome, COUNT(DISTINCT leads.id) AS total
        FROM lead_outcomes
        JOIN leads ON leads.id = lead_outcomes.lead_id
        WHERE leads.assigned_member_id = ?
          AND lead_outcomes.recorded_at >= ? AND lead_outcomes.recorded_at < ?
        GROUP BY lead_outcomes.outcome
        """,
        (member_id, start, end),
    ).fetchall()
    for row in rows:
        if row["outcome"] in STAGE_METRICS:
            counts[STAGE_METRICS[row["outcome"]]] = row["total"]
    return counts


def get_lead(conn, lead_id):
    return conn.execute(
        "SELECT id, source, score, assigned_member_id, created_at FROM leads WHERE id = ?",
        (lead_id,),
    ).fetchone()


def list_outcomes(conn, lead_id):
    return conn.execute(
        "SELECT outcome, recorded_at FROM lead_outcomes WHERE lead_id = ? ORDER BY id",
        (lead_id,),
    ).fetchall()


def list_leads(conn):
    furthest = {}
    for row in conn.execute("SELECT lead_id, outcome FROM lead_outcomes"):
        current = furthest.get(row["lead_id"], "none")
        if OUTCOME_POINTS[row["outcome"]] > OUTCOME_POINTS[current]:
            furthest[row["lead_id"]] = row["outcome"]
    leads = []
    rows = conn.execute(
        "SELECT id, source, score, assigned_member_id, created_at FROM leads ORDER BY id DESC"
    ).fetchall()
    for row in rows:
        leads.append({
            "id": row["id"],
            "source": row["source"],
            "score": row["score"],
            "band": band_for_score(row["score"]),
            "assigned_member_id": row["assigned_member_id"],
            "created_at": row["created_at"],
            "stage": furthest.get(row["id"], "none"),
        })
    return leads

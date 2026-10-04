from datetime import date, timedelta

STAGES = ["none", "showing_booked", "showing_performed", "closed"]
OUTCOME_POINTS = {"none": 0, "showing_booked": 1, "showing_performed": 2, "closed": 4}
EXPECTED_POINTS = {"hot": 2.5, "warm": 1.5, "cold": 0.5}
SCORE_WINDOW_DAYS = 90
HALF_LIFE_DAYS = 30


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
        "UPDATE leads SET assigned_member_id = ? WHERE id = ?",
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

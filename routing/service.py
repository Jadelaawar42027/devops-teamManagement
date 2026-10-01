STAGES = ["none", "showing_booked", "showing_performed", "closed"]


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

# database/build.py
# Fills the database from the files under data/.
#
# The sources stay authoritative:
#
#   hospital_emails_mixed.json  the emails
#   hospital_people.json        the staff
#   history_log.jsonl           every answer, append-only
#
# Nothing is ever only in the database, so it can be deleted and rebuilt
# whenever it drifts. Rebuilding drops the tables first rather than
# updating in place: a half-updated projection is harder to spot than a
# missing one.
#
# Run with:
#     python3 -m database.build

import json
import os
import sqlite3

DB_PATH = os.path.join("data", "simulation.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")

EMAILS_JSON = os.path.join("data", "hospital_emails_mixed.json")
PEOPLE_JSON = os.path.join("data", "hospital_people.json")
HISTORY_LOG = os.path.join("data", "history_log.jsonl")


def domain_of(address):
    return address.rsplit("@", 1)[1].lower() if address and "@" in address else ""


def _schema():
    with open(SCHEMA_PATH) as f:
        return f.read()


# ------------------------------------------------------------------ filling

def load_emails(conn, path=EMAILS_JSON):
    with open(path) as f:
        emails = json.load(f)["emails"]

    for e in emails:
        phishing = e["label"] == "phishing"
        conn.execute(
            "INSERT OR REPLACE INTO emails VALUES (:id, :label, :is_fake,"
            " :cue, :technique, :technique_category, :table_row, :week,"
            " :cia_hit, :address_trick, :key_defense, :target_role,"
            " :difficulty, :sender_name, :sender_email, :sender_domain,"
            " :reply_to, :subject, :body, :link_text, :link_target,"
            " :teaches, :topic)",
            {
                "id": e["id"],
                "label": e["label"],
                "is_fake": 1 if phishing else 0,
                # The attack columns only mean something on a fake.
                "cue": e.get("cue") if phishing else None,
                "technique": e.get("technique") if phishing else None,
                "technique_category": e.get("technique_category") if phishing else None,
                "table_row": e.get("table_row") if phishing else None,
                "week": e.get("week") if phishing else None,
                "cia_hit": e.get("cia_hit") if phishing else None,
                "address_trick": e.get("address_trick") if phishing else None,
                "key_defense": e.get("key_defense"),
                "target_role": e.get("target_role"),
                "difficulty": e.get("difficulty"),
                "sender_name": e.get("sender_name"),
                "sender_email": e.get("sender_email"),
                "sender_domain": domain_of(e.get("sender_email", "")),
                "reply_to": e.get("reply_to"),
                "subject": e.get("subject"),
                "body": e.get("body"),
                "link_text": e.get("link_text"),
                "link_target": e.get("link_target"),
                "teaches": e.get("teaches"),
                "topic": e.get("topic"),
            })

        for n, flag in enumerate(e.get("red_flags") or []):
            conn.execute("INSERT OR REPLACE INTO red_flags VALUES (?, ?, ?)",
                         (e["id"], n, flag))
    return len(emails)


def load_people(conn, path=PEOPLE_JSON):
    with open(path) as f:
        people = json.load(f)["people"]

    for p in people:
        sim = p.get("simulation", {})
        conn.execute(
            "INSERT OR REPLACE INTO people VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?,"
            " ?, ?, ?, ?, ?)",
            (p["job_id"], p["name"], p.get("job_title"), p.get("pillar"),
             p.get("department"), p.get("location"), p.get("age"),
             p.get("gender"), p.get("years_in_role"),
             p.get("years_with_organization"), sim.get("role_group"),
             sim.get("security_awareness"), sim.get("workload"),
             sim.get("shift")))

        # Kept apart from the person on purpose - see schema.sql.
        for cue, prob in (sim.get("hidden_probs") or {}).items():
            conn.execute("INSERT OR REPLACE INTO hidden_probs VALUES (?, ?, ?)",
                         (p["job_id"], cue, prob))
    return len(people)


def load_deliveries(conn, path=HISTORY_LOG):
    """Replay the append-only log into the deliveries table."""
    if not os.path.exists(path):
        return 0, 0

    rows, damaged = [], 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                # A half-written final line from a crash. Every complete
                # line before it is still good.
                damaged += 1
                continue
            if not r.get("person_id"):
                damaged += 1
                continue
            rows.append((
                r.get("n"), r.get("time"), r.get("source"), r["person_id"],
                r.get("email_id"), r.get("subject"), r.get("label"),
                r.get("cue"), r.get("key"), r.get("action"), r.get("said"),
                r.get("truth"),
                int(bool(r.get("correct"))) if "correct" in r else None,
                int(bool(r.get("recognised"))) if "recognised" in r else None,
                r.get("yes"), r.get("no"), r.get("all"),
                r.get("p_before"), r.get("p_click"),
            ))

    conn.executemany(
        "INSERT INTO deliveries (n, at, source, person_id, email_id, subject,"
        " label, cue, cue_key, action, said, truth, correct, recognised,"
        " running_yes, running_no, running_all, p_before, p_click)"
        " VALUES (%s)" % ",".join("?" * 19), rows)
    return len(rows), damaged


# ------------------------------------------------------------------- build

def build(path=DB_PATH, verbose=False):
    """(Re)build the whole database. Safe to run repeatedly."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    if os.path.exists(path):
        os.remove(path)

    conn = sqlite3.connect(path)
    conn.executescript(_schema())

    counts = {
        "emails": load_emails(conn),
        "people": load_people(conn),
    }
    counts["deliveries"], counts["damaged"] = load_deliveries(conn)
    counts["red_flags"] = conn.execute(
        "SELECT COUNT(*) FROM red_flags").fetchone()[0]
    conn.commit()

    if verbose:
        for name in ("emails", "red_flags", "people", "deliveries"):
            print("   %-12s %6d" % (name, counts[name]))
        if counts["damaged"]:
            print("   %-12s %6d (skipped)" % "damaged", counts["damaged"])

    conn.close()
    return counts


def main():
    print("Building %s" % DB_PATH)
    counts = build(verbose=True)
    size = os.path.getsize(DB_PATH) / 1e6
    print("\n%.1f MB" % size)


if __name__ == "__main__":
    main()

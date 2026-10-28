# metrics.py
# Turning the twin's history into tables.
#
# The dashboard, the CSV exports and any notebook all want the same handful
# of rollups. Computing them here means one definition of "click rate"
# rather than one per chart.
#
# Nothing here imports streamlit, and nothing here reads a file: every
# function takes a twin and returns a DataFrame.

import pandas as pd

CUES = ["urgency", "authority", "it_login", "hr_payroll", "billing",
        "false_report"]
PHISH_CUES = CUES[:-1]


def workforce_frame(twin, people):
    """One row per person: what their history says so far.

    Only phishing arrivals count towards the rates. A genuine email that
    someone correctly ignored says nothing about whether they click.
    """
    rows = []
    for p in people:
        events = [e for e in twin.get_history(p.id) if e["label"] == "phishing"]
        answered = [e for e in events if e["action"] in ("click", "report")]
        clicked = sum(1 for e in events if e["action"] == "click")
        reported = sum(1 for e in events if e["action"] == "report")
        rows.append({
            "id": p.id,
            "name": p.name,
            "role": p.job_title,
            "pillar": p.pillar,
            "awareness": p.security_awareness,
            "seen": len(events),
            "answered": len(answered),
            "clicked": clicked,
            "reported": reported,
            "click_rate": clicked / len(events) if events else 0.0,
            "report_rate": reported / len(events) if events else 0.0,
        })
    return pd.DataFrame(rows)


def cue_frame(twin, people):
    """One row per person per cue: how that pressure works on them."""
    rows = []
    for p in people:
        for cue in CUES:
            totals = twin.get_totals(p.id).get(cue)
            if not totals or not totals.get("all"):
                continue
            rows.append({
                "id": p.id,
                "name": p.name,
                "awareness": p.security_awareness,
                "cue": cue,
                "yes": totals["yes"],
                "no": totals["no"],
                "all": totals["all"],
                "p_click": totals["p_click"],
            })
    return pd.DataFrame(rows)


def history_frame(twin, people):
    """Every answered delivery, one row each."""
    rows = []
    for p in people:
        for r in twin.get_history(p.id):
            if "correct" not in r:
                continue
            rows.append({
                "n": r["n"],
                "person_id": p.id,
                "person": p.name,
                "awareness": p.security_awareness,
                "email_id": r["email_id"],
                "subject": r["subject"],
                "label": r["label"],
                "cue": r["cue"],
                "action": r["action"],
                "said": r["said"],
                "correct": r["correct"],
            })
    return pd.DataFrame(rows)

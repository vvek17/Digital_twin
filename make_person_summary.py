# make_person_summary.py
# Counts everything straight from data/history_log.jsonl and writes
# data/person_summary.csv - one row per person, numbered 1 to 25.
#
# Columns:
#   ID                  1 .. 25
#   Emails Received     how many emails reached this person
#   Clicked Phishing    fake emails they trusted and followed  (a mistake)
#   Identified Real     genuine emails they correctly treated as genuine
#   Accuracy (%)        all correct judgements / all emails received
#
# Run with:  python3 make_person_summary.py

import csv
import json
import os

LOG = os.path.join("data", "history_log.jsonl")
PEOPLE = os.path.join("data", "hospital_people.json")
OUT = os.path.join("data", "person_summary.csv")

COLUMNS = [
    "ID", "Person", "Emails Received", "Clicked Phishing",
    "Identified Real", "Caught Phishing", "Flagged Real By Mistake",
    "Accuracy (%)",
]


def read_log(path=LOG):
    """Every answer in the append-only log, skipping any damaged line."""
    rows = []
    if not os.path.exists(path):
        return rows
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue    # half-written final line from a crash
    return rows


def build():
    people = json.load(open(PEOPLE))["people"]
    order = [p["job_id"] for p in people]          # P01 .. P25, in roster order
    names = {p["job_id"]: p["name"] for p in people}

    tally = {pid: {"received": 0, "clicked_phishing": 0, "identified_real": 0,
                   "caught_phishing": 0, "flagged_real": 0}
             for pid in order}

    for r in read_log():
        pid = r.get("person_id")
        if pid not in tally or "correct" not in r:
            continue

        t = tally[pid]
        t["received"] += 1

        phishing = r["truth"] == "spam email"
        said_spam = r["said"] == "spam"

        if phishing:
            if said_spam:
                t["caught_phishing"] += 1      # right
            else:
                t["clicked_phishing"] += 1     # wrong - trusted a fake
        else:
            if said_spam:
                t["flagged_real"] += 1         # wrong - false alarm
            else:
                t["identified_real"] += 1      # right

    rows = []
    for n, pid in enumerate(order, start=1):
        t = tally[pid]
        if not t["received"]:
            continue
        correct = t["caught_phishing"] + t["identified_real"]
        rows.append({
            "ID": n,
            "Person": names[pid],
            "Emails Received": t["received"],
            "Clicked Phishing": t["clicked_phishing"],
            "Identified Real": t["identified_real"],
            "Caught Phishing": t["caught_phishing"],
            "Flagged Real By Mistake": t["flagged_real"],
            "Accuracy (%)": round(100 * correct / t["received"], 1),
        })

    # The four outcome counts must account for every email received.
    for r in rows:
        parts = (r["Clicked Phishing"] + r["Identified Real"]
                 + r["Caught Phishing"] + r["Flagged Real By Mistake"])
        assert parts == r["Emails Received"], \
            "counts do not add up for ID %s" % r["ID"]

    os.makedirs(os.path.dirname(OUT) or ".", exist_ok=True)
    with open(OUT, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    return rows


if __name__ == "__main__":
    rows = build()
    print("Wrote %s: %d people\n" % (OUT, len(rows)))
    print("%-4s %-20s %9s %9s %9s %9s %9s %9s"
          % ("ID", "Person", "Received", "Clicked", "IdReal", "Caught",
             "FalseAlm", "Acc %"))
    print("-" * 84)
    for r in rows:
        print("%-4d %-20s %9d %9d %9d %9d %9d %8.1f%%"
              % (r["ID"], r["Person"][:20], r["Emails Received"],
                 r["Clicked Phishing"], r["Identified Real"],
                 r["Caught Phishing"], r["Flagged Real By Mistake"],
                 r["Accuracy (%)"]))

    total = sum(r["Emails Received"] for r in rows)
    clicked = sum(r["Clicked Phishing"] for r in rows)
    print("-" * 84)
    print("%-25s %9d %9d" % ("TOTAL", total, clicked))

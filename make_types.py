# make_types.py
# Writes data/types.csv: every category used anywhere in the project, with
# how many emails carry it and how many answers it has collected so far.
#
# Two counts, because they answer different questions:
#   emails  - how many of the 51 emails use this type (fixed by the dataset)
#   asked   - how many times it has actually been put in front of someone
#
# A type with emails > 0 and asked = 0 exists but has never been tested.
#
# Run with:  python3 make_types.py

import csv
import json
import os
from collections import Counter

# The attack and address definitions already exist in make_emails.py - import
# them rather than retyping, so the two files can never drift apart.
from make_emails import TAXONOMY, ADDRESS_TRICKS

# Plain-English meaning for every other category. Keyed "category|type".
MEANINGS = {
    # what the email really was
    "ground_truth|phishing": "A fake email. Trusting it is the mistake.",
    "ground_truth|legitimate": "A genuine hospital email. Nothing wrong with it.",

    # the pressure a phishing email applies
    "pressure|urgency": "A deadline or countdown, so you act before you check.",
    "pressure|authority": "Appears to come from someone senior, so refusing feels risky.",
    "pressure|it_login": "Asks you to sign in or verify an account.",
    "pressure|hr_payroll": "About your pay, shifts or benefits - the things nobody ignores.",
    "pressure|billing": "About invoices, payments or supplier accounts.",

    # how obvious the email is
    "difficulty|easy": "The tells are on the surface: odd domain, shouting, bad greeting.",
    "difficulty|hard": "It looks routine. The tell is in the headers, the link or the content.",

    # which part of the CIA triad the attack breaks
    "cia_hit|C": "Confidentiality - only the right people should see the data.",
    "cia_hit|I": "Integrity - the data should be accurate and untampered.",
    "cia_hit|A": "Availability - the system should be there when needed.",
    "cia_hit|C + A": "Breaks confidentiality and availability together.",
    "cia_hit|I + C": "Breaks integrity and confidentiality together.",
    "cia_hit|C, I, A": "Breaks all three at once.",

    # course week
    "week|7": "Week 7 - information security, threats and social engineering.",
    "week|8": "Week 8 - cybersecurity training and DDoS threats.",

    # who the email is aimed at
    "target_role|all": "Sent to every member of staff.",
    "target_role|nurse": "Aimed at nursing staff.",
    "target_role|physician": "Aimed at doctors.",
    "target_role|front_billing": "Aimed at reception and billing staff.",
    "target_role|administration": "Aimed at managers and executives.",

    # the person
    "awareness|low": "Little security training. Clicks most things.",
    "awareness|medium": "Some awareness. Catches the obvious ones.",
    "awareness|high": "Security-aware. Checks before acting and reports.",
    "workload|normal": "Working at a steady pace, so more careful.",
    "workload|busy": "A normal busy day.",
    "workload|very busy": "Slammed right now, so more likely to slip.",
    "shift|day": "Works days.",
    "shift|evening": "Works evenings.",
    "shift|night": "Works nights, when people slip more.",

    # what came out of the answer
    "answer|spam": "They judged it spam and flagged it.",
    "answer|real": "They judged it genuine and trusted it.",
    "clicked|yes": "They trusted a phishing email and followed it.",
    "clicked|no": "They did not follow it.",
    "result|correct": "Their judgement matched what the email actually was.",
    "result|wrong": "Their judgement did not match.",
    "answered_by|a person": "A real person answered in the app.",
    "answered_by|simulation": "The simulated person answered.",
}


def meaning_for(category, value):
    """Plain description of one type, however it is defined."""
    if category == "attack_type":
        tax = TAXONOMY.get(value)
        if tax:
            return "%s. Defense: %s" % (tax["category"], tax["key_defense"])
    if category == "address_trick":
        return ADDRESS_TRICKS.get(value, "")
    return MEANINGS.get("%s|%s" % (category, value), "")

EMAILS_PATH = os.path.join("data", "hospital_emails_mixed.json")
PEOPLE_PATH = os.path.join("data", "hospital_people.json")
HISTORY_CSV = os.path.join("data", "history.csv")
OUT_PATH = os.path.join("data", "types.csv")

# Which column in history.csv corresponds to which field on an email.
EMAIL_FIELDS = [
    ("ground_truth", "label", {"phishing": "phishing", "legitimate": "legitimate"}),
    ("attack_type", "technique", None),
    ("pressure", "cue", None),
    ("difficulty", "difficulty", None),
    ("address_trick", "address_trick", None),
    ("cia_hit", "cia_hit", None),
    ("week", "week", None),
    ("target_role", "target_role", None),
]

# Categories that come from the person, not the email.
PERSON_FIELDS = [("awareness", "security_awareness"), ("workload", "workload"),
                 ("shift", "shift")]

# Categories produced by answering, which no source file lists.
ANSWER_FIELDS = {
    "answer": ["spam", "real"],
    "clicked": ["yes", "no"],
    "result": ["correct", "wrong"],
    "answered_by": ["a person", "simulation"],
}


def load(path, key):
    with open(path) as f:
        return json.load(f)[key]


def history_counts():
    """How many times each value actually appears in the collected answers."""
    counts = {}
    if not os.path.exists(HISTORY_CSV):
        return counts
    with open(HISTORY_CSV) as f:
        for row in csv.DictReader(f):
            for col, value in row.items():
                if value:
                    counts.setdefault(col, Counter())[value] += 1
    return counts


def build():
    emails = load(EMAILS_PATH, "emails")
    people = load(PEOPLE_PATH, "people")
    asked = history_counts()

    rows = []

    def add(category, value, n_emails, n_people=""):
        value = str(value)
        rows.append({
            "category": category,
            "type": value,
            "meaning": meaning_for(category, value),
            "emails": n_emails,
            "people": n_people,
            "asked": asked.get(category, Counter()).get(value, 0),
        })

    # --- categories that live on an email ---
    for column, field, _ in EMAIL_FIELDS:
        counter = Counter()
        for e in emails:
            value = e.get(field)
            # attack_type and pressure are blank on genuine mail, matching
            # how history.csv records them.
            if column in ("attack_type", "pressure", "address_trick",
                          "cia_hit", "week") and e["label"] != "phishing":
                continue
            if value not in (None, ""):
                counter[str(value)] += 1
        for value, n in counter.most_common():
            add(column, value, n)

    # --- categories that live on a person ---
    for column, field in PERSON_FIELDS:
        counter = Counter(str(p["simulation"][field]) for p in people)
        for value, n in counter.most_common():
            add(column, value, "", n)

    # --- categories produced by answering ---
    for column, values in ANSWER_FIELDS.items():
        for value in values:
            add(column, value, "", "")

    os.makedirs(os.path.dirname(OUT_PATH) or ".", exist_ok=True)
    with open(OUT_PATH, "w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["category", "type", "meaning",
                        "emails", "people", "asked"])
        writer.writeheader()
        writer.writerows(rows)

    return rows


if __name__ == "__main__":
    rows = build()
    per_category = Counter(r["category"] for r in rows)

    print("Wrote %s: %d types across %d categories\n"
          % (OUT_PATH, len(rows), len(per_category)))
    print("%-14s %-6s %s" % ("category", "types", "values"))
    print("-" * 78)
    for category, n in per_category.items():
        values = [r["type"] for r in rows if r["category"] == category]
        shown = ", ".join(values[:4])
        if len(values) > 4:
            shown += ", ... (+%d)" % (len(values) - 4)
        print("%-14s %-6d %s" % (category, n, shown[:56]))

    # Which categories history.csv actually has a column for.
    recorded = set()
    if os.path.exists(HISTORY_CSV):
        with open(HISTORY_CSV) as f:
            recorded = set(next(csv.reader(f)))

    not_recorded = sorted({r["category"] for r in rows
                           if r["category"] not in recorded})
    if not_recorded:
        print("\nTracked on the emails but not stored in history.csv:")
        for c in not_recorded:
            n = sum(1 for r in rows if r["category"] == c)
            print("   %-14s %d types" % (c, n))

    never = [r for r in rows if r["asked"] == 0 and r["emails"]
             and r["category"] in recorded]
    if never:
        print("\nIn the email set but never asked yet:")
        for r in never:
            print("   %s = %s (%s emails)" % (r["category"], r["type"], r["emails"]))

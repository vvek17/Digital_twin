# make_people.py
# Generates a fictional hospital staff list for a phishing-awareness simulation.
# Everything here is made up: fake names, a fake hospital, and an ".example" domain.
#
# Output: data/hospital_people.json
#
# Each person gets "hidden_probs": secret click/report chances that belong ONLY
# to the simulated human. The twin predictor must NEVER read these directly.

import json
import os
import random

# A fixed seed makes the output repeatable: run it twice, get the same people.
random.seed(42)


# ---------------------------------------------------------------------------
# 1. The hospital (fictional)
# ---------------------------------------------------------------------------
HOSPITAL = {
    "name": "Ashbrook General Hospital",
    "email_domain": "ashbrookgeneral.example",
    "beds": 320,
    "departments": [
        "Emergency",
        "Ward 4 (Medical)",
        "Surgery",
        "Pediatrics",
        "Radiology",
        "Main Reception",
        "Outpatient Clinic",
        "Finance & Billing",
    ],
}


# ---------------------------------------------------------------------------
# 2. Starting click chances per role
#    These are the "base" probabilities before we adjust for each person.
#    Cues: urgency, authority, it_login, hr_payroll, billing
#    Plus false_report: chance of mistakenly reporting a *real* (safe) email.
# ---------------------------------------------------------------------------
BASE_PROBS = {
    "nurse": {
        "urgency": 0.60, "authority": 0.50, "it_login": 0.40,
        "hr_payroll": 0.70, "billing": 0.10, "false_report": 0.15,
    },
    "doctor": {
        "urgency": 0.50, "authority": 0.40, "it_login": 0.40,
        "hr_payroll": 0.30, "billing": 0.05, "false_report": 0.10,
    },
    "front_desk": {
        "urgency": 0.50, "authority": 0.50, "it_login": 0.60,
        "hr_payroll": 0.50, "billing": 0.40, "false_report": 0.20,
    },
    "admin_billing": {
        "urgency": 0.40, "authority": 0.60, "it_login": 0.40,
        "hr_payroll": 0.40, "billing": 0.60, "false_report": 0.10,
    },
}

# The five "click" cues (everything in hidden_probs except false_report).
CLICK_CUES = ["urgency", "authority", "it_login", "hr_payroll", "billing"]


# ---------------------------------------------------------------------------
# 3. Fake names and how many people of each role we want.
# ---------------------------------------------------------------------------
# How many of each role (10 + 8 + 6 + 6 = 30 people total).
ROLE_COUNTS = {
    "nurse": 10,
    "front_desk": 8,
    "doctor": 6,
    "admin_billing": 6,
}

# Which departments make sense for each role.
ROLE_DEPARTMENTS = {
    "nurse": ["Emergency", "Ward 4 (Medical)", "Surgery", "Pediatrics"],
    "doctor": ["Emergency", "Surgery", "Pediatrics", "Radiology"],
    "front_desk": ["Main Reception", "Outpatient Clinic"],
    "admin_billing": ["Finance & Billing"],
}

# A pool of fictional names to draw from (first + last).
FIRST_NAMES = [
    "Ava", "Liam", "Noah", "Mia", "Ethan", "Sofia", "Lucas", "Isla",
    "Mason", "Zoe", "Leo", "Nora", "Owen", "Ruby", "Finn", "Elise",
    "Kai", "Maya", "Jonah", "Clara", "Theo", "Hana", "Milo", "Iris",
    "Felix", "Nina", "Oscar", "Lena", "Hugo", "Priya",
]
LAST_NAMES = [
    "Carter", "Ahmed", "Nguyen", "Patel", "Brooks", "Reyes", "Flynn",
    "Okafor", "Moreno", "Walsh", "Kaur", "Dubois", "Rossi", "Haddad",
    "Larsen", "Mendez", "Osei", "Park", "Cohen", "Novak",
    "Fisher", "Ortiz", "Khan", "Webb", "Ivanov", "Sato", "Mwangi",
    "Bauer", "Costa", "Lindqvist",
]

SHIFTS = ["day", "evening", "night"]
AWARENESS_LEVELS = ["low", "medium", "high"]
WORKLOAD_LEVELS = ["normal", "busy", "very busy"]


# ---------------------------------------------------------------------------
# 4. Helper: keep a probability inside the allowed range.
# ---------------------------------------------------------------------------
def clamp(value, low=0.02, high=0.95):
    """Force value to stay between low and high."""
    return max(low, min(high, value))


# ---------------------------------------------------------------------------
# 5. Build the hidden_probs for one person, adjusting the base numbers
#    for their awareness, workload, and a little bit of randomness.
# ---------------------------------------------------------------------------
def make_hidden_probs(role, awareness, workload):
    base = BASE_PROBS[role]
    probs = {}

    # --- Click cues (urgency, authority, it_login, hr_payroll, billing) ---
    for cue in CLICK_CUES:
        value = base[cue]

        # Awareness: more awareness means fewer clicks.
        if awareness == "low":
            value += 0.10
        elif awareness == "high":
            value -= 0.15
        # "medium" adds 0.

        # Workload: busier people are a bit more likely to slip.
        if workload == "normal":
            value -= 0.05
        elif workload == "very busy":
            value += 0.08
        # "busy" adds 0.

        # A small random nudge between -0.10 and +0.10.
        value += random.uniform(-0.10, 0.10)

        probs[cue] = round(clamp(value), 3)

    # --- false_report (mistakenly reporting a real email) ---
    fr = base["false_report"]
    if awareness == "low":
        fr -= 0.05          # less careful -> less likely to flag a real email
    elif awareness == "high":
        fr += 0.05          # more careful -> more likely to over-report
    fr += random.uniform(-0.05, 0.05)
    probs["false_report"] = round(clamp(fr), 3)

    return probs


# ---------------------------------------------------------------------------
# 6. Build all 30 people.
# ---------------------------------------------------------------------------
def make_people():
    people = []

    # Shuffle the name pools so names get handed out in a random (but seeded) order.
    first_pool = FIRST_NAMES[:]
    last_pool = LAST_NAMES[:]
    random.shuffle(first_pool)
    random.shuffle(last_pool)

    person_number = 1
    for role, count in ROLE_COUNTS.items():
        for _ in range(count):
            # Pick a name (pop so each name is used once).
            first = first_pool.pop()
            last = last_pool.pop()
            name = first + " " + last

            # Pick traits.
            department = random.choice(ROLE_DEPARTMENTS[role])
            shift = random.choice(SHIFTS)
            years = random.randint(1, 25)
            awareness = random.choice(AWARENESS_LEVELS)
            workload = random.choice(WORKLOAD_LEVELS)

            person = {
                "id": "P%02d" % person_number,          # P01 .. P30
                "name": name,
                "role": role,
                "department": department,
                "shift": shift,
                "years_experience": years,
                "security_awareness": awareness,
                "workload": workload,
                # Secret numbers: only the simulated human may use these.
                "hidden_probs": make_hidden_probs(role, awareness, workload),
            }
            people.append(person)
            person_number += 1

    return people


# ---------------------------------------------------------------------------
# 7. Write everything to data/hospital_people.json.
# ---------------------------------------------------------------------------
def main():
    people = make_people()

    output = {
        "hospital": HOSPITAL,
        "people": people,
    }

    os.makedirs("data", exist_ok=True)
    out_path = os.path.join("data", "hospital_people.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)

    print("Wrote %d people to %s" % (len(people), out_path))


if __name__ == "__main__":
    main()

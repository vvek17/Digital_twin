# Persona: describes one person on the hospital workforce.
# It exposes the realistic HR fields AND the phishing-simulation behavior.
#
# IMPORTANT:
#   hidden_probs are the person's SECRET click/report chances. They live inside
#   the "simulation" block and belong ONLY to the simulated human (human.py).
#   The twin predictor (twin.py) must NEVER read hidden_probs -- its job is to
#   GUESS them from what it observes.

import json


class Persona:
    def __init__(self, data):
        # "data" is one person's dictionary from hospital_people.json.

        # --- Realistic workforce fields (visible to anyone, incl. the twin) ---
        self.id = data["job_id"]
        self.name = data["name"]
        self.age = data.get("age")
        self.gender = data.get("gender")
        self.job_title = data["job_title"]
        self.role = data["job_title"]            # friendly alias used for display
        self.pillar = data.get("pillar")
        self.department = data.get("department")
        self.location = data.get("location")
        self.years_in_role = data.get("years_in_role")
        self.years_with_organization = data.get("years_with_organization")

        # --- Phishing-simulation behavior (from the "simulation" block) ---
        sim = data.get("simulation", {})
        self.role_group = sim.get("role_group")
        self.security_awareness = sim.get("security_awareness")
        self.workload = sim.get("workload")
        self.shift = sim.get("shift")
        # SIMULATED HUMAN ONLY -- never the twin.
        self.hidden_probs = sim.get("hidden_probs", {})

    def describe(self):
        # Short, readable summary (visible fields only).
        return "%s (%s) - %s, %s, awareness=%s, workload=%s" % (
            self.name, self.id, self.job_title, self.department,
            self.security_awareness, self.workload,
        )


def load_people(file_path="data/hospital_people.json"):
    """Load every person from the JSON file and return a list of Persona objects."""
    with open(file_path) as f:
        data = json.load(f)
    return [Persona(person) for person in data["people"]]

# Persona: describes one simulated person on the hospital staff.
# It holds the traits that shape how that person reacts to emails.
#
# IMPORTANT:
#   hidden_probs are the person's SECRET click/report chances.
#   They belong ONLY to the simulated human (human.py), which uses them to
#   decide what action to take. The twin predictor (twin.py) must NEVER read
#   hidden_probs directly -- its whole job is to *guess* those chances from
#   the visible traits. Peeking would be cheating.

import json


class Persona:
    def __init__(self, data):
        # "data" is one person's dictionary loaded from the JSON file.

        # --- Visible traits (anyone, including the twin, may use these) ---
        self.id = data["id"]
        self.name = data["name"]
        self.role = data["role"]
        self.department = data["department"]
        self.shift = data["shift"]
        self.years_experience = data["years_experience"]
        self.security_awareness = data["security_awareness"]
        self.workload = data["workload"]

        # --- Hidden traits (SIMULATED HUMAN ONLY -- never the twin) ---
        self.hidden_probs = data["hidden_probs"]

    def describe(self):
        # Return a short, readable summary of this persona (visible traits only).
        return "%s (%s) - %s, %s, awareness=%s, workload=%s" % (
            self.name,
            self.id,
            self.role,
            self.department,
            self.security_awareness,
            self.workload,
        )


def load_people(file_path="data/hospital_people.json"):
    """Load every person from the JSON file and return a list of Persona objects."""
    with open(file_path) as f:
        data = json.load(f)

    personas = []
    for person in data["people"]:
        personas.append(Persona(person))
    return personas

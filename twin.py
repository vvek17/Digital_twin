# TwinPredictor: the "digital twin" model.
# Its job is to GUESS how a person will react to an email.
#
# How it learns:
#   The twin keeps simple counters for each person (looked up by person id).
#   It watches what the person actually does (through update()) and slowly
#   builds up a guess. It starts knowing nothing and gets better with data.
#
# For every counter we keep two numbers, a and b, and the guess is:
#       chance = a / (a + b)
#   Both start at 1. Starting at 1 (instead of 0) avoids dividing by zero and
#   means an unseen cue starts at a neutral guess of 1/2 = 0.5 ("no idea yet").
#
# IMPORTANT: The twin must NEVER read hidden_probs. Those are the person's
# secret numbers. The twin is only allowed to learn from the actions it sees.


class TwinPredictor:
    def __init__(self):
        # One entry per person id, e.g. "P05".
        # Each person gets a set of counters, one pair per cue.
        self.counters = {}

    def _counters_for(self, person_id):
        """Return this person's counters, creating fresh ones the first time."""
        if person_id not in self.counters:
            # Every pair is {"a": 1, "b": 1} to start (neutral 0.5 guess).
            self.counters[person_id] = {
                # --- phishing cues: a = clicked, b = did NOT click ---
                "urgency":      {"a": 1, "b": 1},
                "authority":    {"a": 1, "b": 1},
                "it_login":     {"a": 1, "b": 1},
                "hr_payroll":   {"a": 1, "b": 1},
                "billing":      {"a": 1, "b": 1},
                # --- legitimate emails: a = reported by mistake, b = did not ---
                "false_report": {"a": 1, "b": 1},
            }
        return self.counters[person_id]

    def _key_for(self, email):
        """Which counter does this email use?"""
        if email["label"] == "phishing":
            return email["cue"]        # e.g. "urgency"
        else:
            return "false_report"      # a real/safe email

    def predict(self, person_id, email):
        """Return the twin's current guess (0.0 to 1.0) for this person + email."""
        counts = self._counters_for(person_id)
        key = self._key_for(email)
        a = counts[key]["a"]
        b = counts[key]["b"]
        return a / (a + b)

    def update(self, person_id, email, action):
        """After the human acts, add 1 to the matching counter."""
        counts = self._counters_for(person_id)
        key = self._key_for(email)

        if email["label"] == "phishing":
            # For phishing we care about clicking.
            # Our simulated human only clicks or ignores a phishing email,
            # so "a" counts clicks and "b" counts every time they did not click.
            if action == "click":
                counts[key]["a"] += 1
            else:
                counts[key]["b"] += 1
        else:
            # For a real email we care about a false alarm (reporting it).
            if action == "report":
                counts[key]["a"] += 1
            else:
                counts[key]["b"] += 1

    def get_all_estimates(self, person_id):
        """Return all of the twin's current guesses for this person as a dict."""
        counts = self._counters_for(person_id)
        estimates = {}
        for key, pair in counts.items():
            estimates[key] = pair["a"] / (pair["a"] + pair["b"])
        return estimates

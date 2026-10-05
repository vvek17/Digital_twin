# EmailGenerator: creates simulated phishing (and maybe safe) emails.
# Later this will build emails with different tricks and difficulty levels.


import json
import random

class EmailGenerator:
    def __init__(self, file_path="data/hospital_emails_mixed.json"):
        with open(file_path) as f:
            data = json.load(f)
        self.emails = data["emails"]

    def get_email(self, role=None):
        if role:
            options = [e for e in self.emails
                       if e["target_role"] in (role, "all")]
        else:
            options = self.emails
        return random.choice(options)
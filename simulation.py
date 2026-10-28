# Simulation: connects all the pieces and runs the experiment automatically.
#
# One round is the full loop from the diagram:
#
#     email  ->  twin.predict()        (Model -> Predict click prob)
#            ->  human.respond()       (Human -> Click or Report)
#            ->  twin.update()         (Compare and update)
#            ->  feedback.give_feedback()  (Personalized feedback)
#
# Nobody clicks anything: the simulated human answers from its own hidden_probs
# and the situation, so a whole run finishes in one call.
#
# The twin predicts BEFORE the human acts, so every prediction is scored on an
# email it has not seen the answer to yet.

from situation import make_random_situation


class Simulation:
    def __init__(self, persona, generator, human, twin, feedback,
                 use_situations=True, allow_repeats=False):
        self.persona = persona
        self.generator = generator
        self.human = human
        self.twin = twin
        self.feedback = feedback
        self.use_situations = use_situations
        # With repeats on, an email can arrive again at a different moment.
        # That only carries information if the reader reacts to the moment.
        self.allow_repeats = allow_repeats

        # One record per round, in order.
        self.rounds = []

    def step(self):
        """Run exactly one round and return its record.

        Returns None once this person has seen every email: a test asks each
        question once, so there is nothing left to ask.
        """
        if self.allow_repeats:
            email = self.generator.get_email()
        else:
            seen = {r["email_id"] for r in self.twin.get_history(self.persona.id)}
            email = self.generator.get_unseen(seen)
            if email is None:
                return None
        situation = make_random_situation() if self.use_situations else None

        # 1. Model predicts, from history alone.
        predicted = self.twin.predict(self.persona.id, email)

        # 2. Human acts.
        action = self.human.respond(email, situation)

        # 3. Compare and update.
        self.twin.update(self.persona.id, email, action)

        # 4. Feedback, from the history that now includes this answer.
        key = "false_report" if email["label"] == "legitimate" else email["cue"]
        note = self.feedback.give_feedback(
            email, action, self.twin.get_history(self.persona.id, key)
        )

        record = {
            "round": len(self.rounds) + 1,
            "email_id": email["id"],
            "subject": email["subject"],
            "label": email["label"],
            "cue": email["cue"],
            "key": key,
            "technique": email.get("technique"),
            "situation": situation,
            "predicted": round(predicted, 3),
            "action": action,
            "after": round(self.twin.predict(self.persona.id, email), 3),
            "feedback": note,
        }
        self.rounds.append(record)
        return record

    def run(self, num_rounds):
        """Run up to num_rounds times, stopping early if the emails run out."""
        for _ in range(num_rounds):
            if self.step() is None:
                break
        return self.rounds

    # ------------------------------------------------------------------ stats

    def results(self):
        """Summarise the run: what the person did, and how well the twin did."""
        phishing = [r for r in self.rounds if r["label"] == "phishing"]
        legit = [r for r in self.rounds if r["label"] == "legitimate"]

        def share(records, action):
            if not records:
                return 0.0
            return sum(1 for r in records if r["action"] == action) / len(records)

        # How close the twin's final guesses are to the real hidden numbers.
        # hidden_probs is read ONLY here, to grade the twin, never by the twin.
        estimates = self.twin.get_all_estimates(self.persona.id)
        gaps = {}
        for cue, truth in self.persona.hidden_probs.items():
            if cue in estimates:
                gaps[cue] = abs(estimates[cue] - truth)

        return {
            "person": self.persona.name,
            "person_id": self.persona.id,
            "rounds": len(self.rounds),
            "phishing_seen": len(phishing),
            "legitimate_seen": len(legit),
            "click_rate": share(phishing, "click"),
            "report_rate": share(phishing, "report"),
            "ignore_rate": share(phishing, "ignore"),
            "false_alarm_rate": share(legit, "report"),
            "estimates": estimates,
            "hidden_probs": dict(self.persona.hidden_probs),
            "gaps": gaps,
            "avg_error": sum(gaps.values()) / len(gaps) if gaps else 0.0,
        }

    def per_cue(self):
        """One row per cue: how often it was seen, clicked, reported, and the guess."""
        rows = {}
        for r in self.rounds:
            key = r["key"]
            row = rows.setdefault(key, {"cue": key, "seen": 0, "clicked": 0, "reported": 0})
            row["seen"] += 1
            if r["action"] == "click":
                row["clicked"] += 1
            elif r["action"] == "report":
                row["reported"] += 1

        estimates = self.twin.get_all_estimates(self.persona.id)
        for key, row in rows.items():
            row["twin_guess"] = round(estimates.get(key, 0.0), 3)
            row["actual"] = round(self.persona.hidden_probs.get(key, 0.0), 3)
        return sorted(rows.values(), key=lambda r: r["cue"])

# SimulatedHuman: stands in for a real person receiving emails.
# It decides to click, report, or ignore an email based on its Persona.
#
# Two layers decide an action:
#   1. PERSONALITY  -> the person's fixed hidden_probs (never changes)
#   2. SITUATION    -> the moment the email arrives (changes every email)
# The situation nudges the personality's click chance up or down.

import random


class SimulatedHuman:
    def __init__(self, persona):
        # Remember WHO this human is (their traits + secret hidden_probs).
        self.persona = persona

    def respond(self, email, situation=None):
        """Decide what to do with an email: 'click', 'report', or 'ignore'.

        situation is optional. If None, the person behaves normally (no nudges),
        so older code that calls respond(email) still works.
        """
        if email["label"] == "phishing":
            # Start from the personality's secret chance for this trick.
            cue = email["cue"]
            chance = self.persona.hidden_probs[cue]

            # Let the current situation nudge that chance up or down.
            chance = self._adjust_for_situation(chance, email, situation)

            # Roll the dice against the final chance.
            if random.random() < chance:
                return "click"

            # They did not click. A security-aware person goes one step further
            # and REPORTS it; everyone else just leaves it in the inbox.
            if random.random() < self._report_chance(situation):
                return "report"
            return "ignore"
        else:
            # A real/safe email: the only mistake is a false alarm.
            chance = self.persona.hidden_probs["false_report"]
            if random.random() < chance:
                return "report"
            else:
                return "ignore"

    # How likely someone is to REPORT a phishing email they did not click.
    # There is no hidden_probs entry for this, so it comes from the one trait
    # that drives it: how security-aware the person is.
    REPORT_CHANCE = {"high": 0.50, "medium": 0.25, "low": 0.10}

    def _report_chance(self, situation):
        """Chance of reporting a phishing email that was not clicked."""
        chance = self.REPORT_CHANCE.get(self.persona.security_awareness, 0.25)

        # Mid-rush, raising a ticket is the first thing to get dropped.
        if situation and situation.get("busy_now") == "very busy":
            chance -= 0.05

        return max(0.02, min(0.95, chance))

    def _adjust_for_situation(self, chance, email, situation):
        """Nudge the click chance based on the moment the email arrives.

        This is where shift and department finally matter.
        """
        if situation is None:
            return chance   # no situation given -> behave normally

        # 1) Night is tiring: people slip more at night.
        if situation.get("time_of_day") == "night":
            chance += 0.10

        # 2) An email that lands DURING your own shift feels expected/normal,
        #    so you are a bit more likely to act on it.
        if situation.get("time_of_day") == self.persona.shift:
            chance += 0.05

        # 3) A rush RIGHT NOW makes people careless; a calm moment makes them careful.
        if situation.get("busy_now") == "very busy":
            chance += 0.10
        elif situation.get("busy_now") == "normal":
            chance -= 0.05

        # 4) A billing email to the Finance team looks like their normal work,
        #    so it lowers their guard.
        if email["cue"] == "billing" and self.persona.department == "Finance & Billing":
            chance += 0.10

        # Keep the final chance sensible (same 0.02..0.95 rule as the data).
        return max(0.02, min(0.95, chance))

    def learn(self, feedback):
        # Will update behaviour after receiving feedback (feedback stage, later).
        pass

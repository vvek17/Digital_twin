"""Compatibility name for automatic answers that inspect the email.

Older scripts import SimulatedHuman. Keep that interface, but use the existing
RuleReader instead of hidden probabilities or random answer selection.
"""

from backend.reader import RuleReader


class SimulatedHuman:
    def __init__(self, persona):
        self.persona = persona
        self.reader = RuleReader(persona)

    def respond(self, email, situation=None):
        """Choose an action from the email's contents and the reader's checks."""
        return self.reader.respond(email, situation)

    def learn(self, feedback):
        # Kept for existing callers; feedback does not change the reader.
        pass

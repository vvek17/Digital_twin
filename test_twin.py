# test_twin.py
# A small experiment:
#   - pick one person
#   - send them 30 random emails
#   - for each email: twin guesses -> human acts -> twin learns
#   - then compare the twin's final guesses to the person's REAL hidden_probs
#
# Note: this test script peeks at hidden_probs ONLY to grade the twin, like an
# examiner holding the answer key. The twin itself never sees them.

import random

from persona import load_people
from generator import EmailGenerator
from human import SimulatedHuman
from twin import TwinPredictor

# Fixed seed so the experiment gives the same result every run.
random.seed(42)

# How many emails to send.
NUM_EMAILS = 30


def main():
    # 1. Load the people and the emails.
    people = load_people()
    generator = EmailGenerator()

    # 2. Pick one person (P05 here) and build their simulated human + the twin.
    person = people[4]
    human = SimulatedHuman(person)
    twin = TwinPredictor()

    print("Person: %s (%s)" % (person.name, person.id))
    print("Role: %s | awareness: %s | workload: %s"
          % (person.role, person.security_awareness, person.workload))
    print("Sending %d random emails...\n" % NUM_EMAILS)

    # 3. Send NUM_EMAILS random emails, one at a time.
    for _ in range(NUM_EMAILS):
        email = generator.get_email()          # a random email

        # The loop you described: predict -> act -> update.
        twin.predict(person.id, email)         # twin makes its guess first
        action = human.respond(email)          # the human reacts
        twin.update(person.id, email, action)  # twin learns from what happened

    # 4. Compare the twin's final guesses to the real hidden_probs.
    estimates = twin.get_all_estimates(person.id)

    print("%-14s %-12s %-14s %-10s" %
          ("cue", "twin guess", "real (hidden)", "difference"))
    print("-" * 52)
    for cue in ["urgency", "authority", "it_login",
                "hr_payroll", "billing", "false_report"]:
        guess = estimates[cue]
        real = person.hidden_probs[cue]
        diff = abs(guess - real)
        print("%-14s %-12.2f %-14.2f %-10.2f" % (cue, guess, real, diff))


if __name__ == "__main__":
    main()

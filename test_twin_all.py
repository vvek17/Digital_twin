# test_twin_all.py
# Runs the twin for EVERY person and shows how accurate it was for each one.
#
# For each person:
#   - send them NUM_EMAILS random emails (predict -> act -> update)
#   - then compare the twin's final guesses to the real hidden_probs
#   - "error" = average gap between guess and reality across all cues
#     (smaller error = the twin predicted that person better)
#
# Note: hidden_probs is read ONLY here, to grade the twin. The twin never sees it.

import random

from persona import load_people
from generator import EmailGenerator
from human import SimulatedHuman
from twin import TwinPredictor

# Same seed every run so the numbers are repeatable.
random.seed(42)

# How many emails each person gets. More emails = the twin learns better.
NUM_EMAILS = 100

# The cues we compare (the 5 click cues + false_report).
CUES = ["urgency", "authority", "it_login", "hr_payroll", "billing", "false_report"]


def average_error(twin, person):
    """Average gap between the twin's guess and the real hidden chance."""
    estimates = twin.get_all_estimates(person.id)
    total = 0.0
    for cue in CUES:
        total += abs(estimates[cue] - person.hidden_probs[cue])
    return total / len(CUES)


def main():
    people = load_people()
    generator = EmailGenerator()
    # No file paths: a test must never write into the real history.
    twin = TwinPredictor(log_path=None, csv_path=None, results_path=None)   # separate counters per person id

    # Run the simulation for every person.
    for person in people:
        human = SimulatedHuman(person)
        for _ in range(NUM_EMAILS):
            email = generator.get_email()
            twin.predict(person.id, email)
            action = human.respond(email)
            twin.update(person.id, email, action)

    # Work out each person's error, then sort best (smallest error) first.
    rows = []
    for person in people:
        rows.append((average_error(twin, person), person))
    rows.sort(key=lambda r: r[0])

    print("Twin accuracy per person (%d emails each, best first)\n" % NUM_EMAILS)
    print("%-5s %-16s %-14s %-10s" % ("id", "name", "role", "avg error"))
    print("-" * 50)

    total = 0.0
    for error, person in rows:
        total += error
        print("%-5s %-16s %-14s %-10.3f"
              % (person.id, person.name, person.role, error))

    print("-" * 50)
    print("%-37s %-10.3f" % ("overall average error", total / len(rows)))
    print("\n(lower error = the twin predicted that person more accurately)")


if __name__ == "__main__":
    main()

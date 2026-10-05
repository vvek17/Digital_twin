# test_situation.py
# Proof that the SITUATION matters:
# the SAME person and the SAME phishing email, under a calm moment vs a
# chaotic moment, give very different click rates.

import random

from persona import load_people
from generator import EmailGenerator
from human import SimulatedHuman

# Fixed seed so the numbers are the same every run.
random.seed(42)

# How many times to repeat each test (more tries = smoother percentages).
TRIES = 2000


def click_rate(human, email, situation):
    """Send the same email many times and return the fraction that were clicked."""
    clicks = 0
    for _ in range(TRIES):
        if human.respond(email, situation) == "click":
            clicks += 1
    return clicks / TRIES


def main():
    people = load_people()
    generator = EmailGenerator()

    # Pick one person.
    person = people[4]
    human = SimulatedHuman(person)

    # Pick one phishing email to test with.
    phishing_emails = [e for e in generator.emails if e["label"] == "phishing"]
    email = phishing_emails[0]
    cue = email["cue"]

    print("Person: %s (%s) | shift: %s | department: %s"
          % (person.name, person.id, person.shift, person.department))
    print("Email cue: %s | base hidden chance: %.2f\n"
          % (cue, person.hidden_probs[cue]))

    # Two very different moments.
    calm = {"time_of_day": "day", "busy_now": "normal"}
    chaotic = {"time_of_day": "night", "busy_now": "very busy"}

    print("%-28s %s" % ("situation", "click rate"))
    print("-" * 42)
    print("%-28s %.0f%%" % ("(no situation / baseline)",
                            click_rate(human, email, None) * 100))
    print("%-28s %.0f%%" % ("calm (day, normal)",
                            click_rate(human, email, calm) * 100))
    print("%-28s %.0f%%" % ("chaotic (night, very busy)",
                            click_rate(human, email, chaotic) * 100))


if __name__ == "__main__":
    main()

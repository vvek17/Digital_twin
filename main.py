# Entry point: creates the components and runs the simulation automatically.
#
# Run with:
#     python3 main.py                  one person, 60 emails
#     python3 main.py P09 200          a chosen person, 200 emails
#     python3 main.py all 100          every person, 100 emails each
#
# Nothing to click: the simulated human answers on its own, the twin learns
# from what it sees, and the feedback module explains each answer.
#
# History is automatic. Every run loads data/people_history.json, adds to it,
# and saves it back, so counters build up across runs. Two switches change that:
#     --fresh      ignore what is on disk and start every counter at 0
#     --no-save    run without writing anything

import random
import sys

from backend.persona import load_people
from backend.generator import EmailGenerator
from backend.human import SimulatedHuman
from backend.reader import RuleReader
from backend.twin import TwinPredictor, HISTORY_PATH
from backend.feedback import FeedbackModule
from backend.simulation import Simulation

SEED = 42
DEFAULT_ROUNDS = 60
SHOW_FIRST = 8          # how many rounds to print in full


def run_one(person, generator, twin, rounds, verbose=True,
            use_reader=False, allow_repeats=False):
    """Run the whole loop for one person and return the finished Simulation."""
    sim = Simulation(
        persona=person,
        generator=generator,
        human=RuleReader(person) if use_reader else SimulatedHuman(person),
        twin=twin,
        feedback=FeedbackModule("detailed"),
        allow_repeats=allow_repeats,
    )
    sim.run(rounds)

    if not sim.rounds:
        # allow_repeats=False and this person has already answered every
        # email in the set, so the run was a no-op. Say so rather than
        # indexing an empty list.
        if verbose:
            print("%s (%s) has already seen every email. "
                  "Use --repeats to ask again."
                  % (person.name, person.id))
        return sim

    if verbose:
        print("=" * 72)
        print("%s (%s) - %s" % (person.name, person.id, person.job_title))
        print("awareness: %s | workload: %s | shift: %s"
              % (person.security_awareness, person.workload, person.shift))
        print("=" * 72)

        print("\nFirst %d rounds\n" % SHOW_FIRST)
        print("%-3s %-5s %-12s %-8s %-8s %-7s" %
              ("#", "email", "cue", "predict", "action", "after"))
        print("-" * 52)
        for r in sim.rounds[:SHOW_FIRST]:
            print("%-3d %-5s %-12s %-8.2f %-8s %-7.2f" %
                  (r["round"], r["email_id"], r["cue"], r["predicted"],
                   r["action"], r["after"]))

        # Show the feedback from the last round, as the person would see it.
        last = sim.rounds[-1]
        if last["feedback"]:
            print("\nFeedback on the final email (%s):" % last["email_id"])
            print(FeedbackModule("detailed").as_text(last["feedback"]))

        print("\nPer cue\n")
        print("%-14s %-6s %-9s %-9s %-11s %-8s" %
              ("cue", "seen", "clicked", "reported", "twin guess", "actual"))
        print("-" * 62)
        for row in sim.per_cue():
            print("%-14s %-6d %-9d %-9d %-11.2f %-8.2f" %
                  (row["cue"], row["seen"], row["clicked"], row["reported"],
                   row["twin_guess"], row["actual"]))

        res = sim.results()
        print("\nSummary")
        print("-" * 52)
        print("rounds              %d (%d phishing, %d legitimate)"
              % (res["rounds"], res["phishing_seen"], res["legitimate_seen"]))
        print("clicked             %.1f%% of phishing" % (100 * res["click_rate"]))
        print("reported            %.1f%% of phishing" % (100 * res["report_rate"]))
        print("ignored             %.1f%% of phishing" % (100 * res["ignore_rate"]))
        print("false alarms        %.1f%% of legitimate" % (100 * res["false_alarm_rate"]))
        print("twin average error  %.3f" % res["avg_error"])

    return sim


def main():
    random.seed(SEED)

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    fresh = "--fresh" in flags
    # --reader answers by inspecting the email instead of rolling against
    # hidden_probs. No invented numbers anywhere in that path.
    use_reader = "--reader" in flags
    # --repeat lets an email arrive more than once, at different moments.
    allow_repeats = bool(flags & {"--repeat", "--repeats"})
    save = "--no-save" not in flags

    who = args[0] if args else None
    rounds = int(args[1]) if len(args) > 1 else DEFAULT_ROUNDS

    people = load_people()
    people_by_id = {p.id: p for p in people}
    generator = EmailGenerator()

    # Carry on from the history already on disk unless asked to start fresh.
    twin = TwinPredictor() if fresh else TwinPredictor.from_log()
    twin.people_by_id = people_by_id
    carried = sum(len(twin.get_history(p.id)) for p in people)
    if carried:
        print("Loaded %d past answers from %s\n" % (carried, HISTORY_PATH))

    if who == "all":
        print("Running %d rounds for each of %d people\n" % (rounds, len(people)))
        print("%-5s %-18s %-10s %-9s %-10s %-9s" %
              ("id", "name", "awareness", "clicked", "reported", "error"))
        print("-" * 68)
        for person in people:
            sim = run_one(person, generator, twin, rounds, verbose=False,
                          use_reader=use_reader, allow_repeats=allow_repeats)
            res = sim.results()
            print("%-5s %-18s %-10s %-9.1f %-10.1f %-9.3f" %
                  (person.id, person.name[:18], person.security_awareness,
                   100 * res["click_rate"], 100 * res["report_rate"], res["avg_error"]))
        if save:
            twin.save(people_by_id=people_by_id)
            twin.write_email_scores({e['id']: e for e in generator.emails})
            total = sum(len(twin.get_history(p.id)) for p in people)
            print("\nHistory saved to %s (%d answers on file)" % (HISTORY_PATH, total))
        return

    if who:
        matches = [p for p in people if p.id == who]
        if not matches:
            print("No person with id %r. Try one of: %s"
                  % (who, ", ".join(p.id for p in people[:5]) + ", ..."))
            return
        person = matches[0]
    else:
        person = people[2]      # a nurse, by default

    run_one(person, generator, twin, rounds, use_reader=use_reader,
            allow_repeats=allow_repeats)

    if save:
        twin.save(people_by_id=people_by_id)
        twin.write_email_scores({e['id']: e for e in generator.emails})
        print("\nHistory saved to %s (%d answers on file for %s)"
              % (HISTORY_PATH, len(twin.get_history(person.id)), person.name))


if __name__ == "__main__":
    main()

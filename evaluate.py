# evaluate.py
# Does what the twin learned transfer to emails it has never seen?
#
# The twin learned each person's click rate per cue from the history. None of
# that history involved the emails built by email_builder.py. So:
#
#   1. build a batch of brand new emails
#   2. ask the twin to PREDICT how each person would do on each one,
#      using only the counters it already has
#   3. let the person actually judge them (the rule reader)
#   4. compare
#
# The twin predicts a probability; the person gives a yes or no. To compare
# them, the prediction is read as "would they fall for it?" - predicted click
# above 0.5 means yes.
#
# The ratio that matters is how often the prediction matched the outcome.
#
# Run with:
#     python3 evaluate.py              200 new emails
#     python3 evaluate.py 1000         more

import collections
import random
import sys

from backend.persona import load_people
from backend.reader import RuleReader
from backend.twin import TwinPredictor
from backend.situation import make_random_situation
from backend.email_builder import EmailBuilder

THRESHOLD = 0.5          # above this, the twin expects them to fall for it


def evaluate(n_emails=200, seed=5):
    random.seed(seed)

    people = load_people()
    # The twin arrives already trained - it replays the saved history and
    # writes nothing, so running this never pollutes the real data.
    twin = TwinPredictor(log_path=None, csv_path=None, results_path=None)
    twin.rebuild_from_log("data/history_log.jsonl")

    trained = sum(len(twin.get_history(p.id)) for p in people)
    if not trained:
        print("No history yet - run the simulation first.")
        return None

    builder = EmailBuilder()
    new_emails = builder.build(n_emails)
    readers = {p.id: RuleReader(p) for p in people}

    rows = []
    for person in people:
        for email in new_emails:
            predicted = twin.predict(person.id, email)
            expect_fall = predicted > THRESHOLD

            action = readers[person.id].respond(email, make_random_situation())

            # "Fell for it" only means something on a phishing email. On a
            # genuine one the matching mistake is a false alarm - flagging
            # real mail as spam - which is what the false_report counter
            # predicts, so compare against that instead.
            if email["label"] == "phishing":
                actually_fell = action != "report"
            else:
                actually_fell = action == "report"   # a false alarm

            rows.append({
                "is_phishing": email["label"] == "phishing",
                "person_id": person.id,
                "awareness": person.security_awareness,
                "email_id": email["id"],
                "technique": email["technique"],
                "cue": email["cue"],
                "predicted": predicted,
                "expected_to_fall": expect_fall,
                "actually_fell": actually_fell,
                "matched": expect_fall == actually_fell,
            })

    return {"rows": rows, "emails": new_emails, "trained_on": trained}


def report(result):
    rows = result["rows"]
    total = len(rows)
    matched = sum(1 for r in rows if r["matched"])

    print("Trained on %d past answers." % result["trained_on"])
    print("Tested on %d brand new emails the twin has never seen.\n"
          % len(result["emails"]))

    print("=" * 58)
    print("  Predictions that matched: %d of %d" % (matched, total))
    print("  RATIO: %.1f%%" % (100 * matched / total))
    print("=" * 58)
    print()

    # Where the prediction went wrong, and in which direction.
    fp = sum(1 for r in rows if r["expected_to_fall"] and not r["actually_fell"])
    fn = sum(1 for r in rows if not r["expected_to_fall"] and r["actually_fell"])
    print("  expected to fall but caught it : %d" % fp)
    print("  expected to catch but fell     : %d" % fn)
    print()

    phish = [r for r in rows if r["is_phishing"]]
    genuine = [r for r in rows if not r["is_phishing"]]
    print("Split by what the email really was")
    print("%-22s %8s %8s %9s" % ("", "tested", "matched", "ratio"))
    print("-" * 52)
    for label, group in (("phishing", phish), ("genuine", genuine)):
        if group:
            m = sum(1 for r in group if r["matched"])
            print("%-22s %8d %8d %8.1f%%"
                  % (label, len(group), m, 100 * m / len(group)))
    print()

    print("By awareness")
    print("%-10s %8s %8s %9s" % ("", "tested", "matched", "ratio"))
    print("-" * 40)
    by = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        b = by[r["awareness"]]
        b[0] += 1
        b[1] += r["matched"]
    for level in ("low", "medium", "high"):
        if level in by:
            t, m = by[level]
            print("%-10s %8d %8d %8.1f%%" % (level, t, m, 100 * m / t))
    print()

    print("By technique (the new emails)")
    print("%-28s %8s %9s" % ("", "tested", "ratio"))
    print("-" * 48)
    byt = collections.defaultdict(lambda: [0, 0])
    for r in rows:
        b = byt[r["technique"]]
        b[0] += 1
        b[1] += r["matched"]
    for name, (t, m) in sorted(byt.items(), key=lambda kv: -kv[1][1] / kv[1][0]):
        print("%-28s %8d %8.1f%%" % (name, t, 100 * m / t))


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    result = evaluate(n)
    if result:
        report(result)

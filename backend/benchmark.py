# benchmark.py
# The head-to-head: machine learning model against the counting twin.
#
# Both are asked the same question about emails neither has seen - "would
# this person fall for this?" - and both are graded against what the person
# actually does. Brand new emails are the whole point: on an email already
# in the history the twin can score well by remembering it.
#
#   ml model      a random forest over person and email features
#   counting twin P(click) = yes / (yes + no) for that cue
#
# A prediction above 0.5 is read as "yes, they would fall for it".
#
# WHAT THIS MEASURES
#
# The person is the rule reader, so both models are being graded on
# reproducing a checklist, not on predicting a human. The comparison between
# the two is fair; the absolute numbers are not evidence about people.
#
# Run with:
#     python3 benchmark.py            200 new emails
#     python3 benchmark.py 1000

import sys

import pandas as pd

from backend.email_builder import EmailBuilder
from backend.ml_model import featurize, train_best
from backend.persona import load_people
from backend.reader import RuleReader
from backend.situation import make_random_situation
from backend.twin import TwinPredictor

THRESHOLD = 0.5


def run(n_emails=200, twin=None, people=None, model=None, feature_cols=None,
        on_progress=None):
    """Score both models on n brand new emails. Returns a DataFrame."""
    people = people or load_people()
    twin = twin or TwinPredictor.from_log()
    if model is None:
        model, feature_cols = train_best()

    new_emails = EmailBuilder().build(int(n_emails))
    readers = {p.id: RuleReader(p) for p in people}

    rows = []
    for i, person in enumerate(people, start=1):
        # One batch per person: the model scores every email at once, which
        # is far faster than a call per email.
        feats = pd.DataFrame(
            [featurize(person, e) for e in new_emails])[feature_cols]
        ml_prob = model.predict_proba(feats)[:, 1]

        for email, prob in zip(new_emails, ml_prob):
            twin_prob = twin.predict(person.id, email)
            fell = readers[person.id].respond(
                email, make_random_situation()) != "report"
            rows.append({
                "person": person.name,
                "awareness": person.security_awareness,
                "email": email["id"],
                "technique": email["technique"],
                "ml_says_falls": bool(prob > THRESHOLD),
                "twin_says_falls": bool(twin_prob > THRESHOLD),
                "actually_fell": fell,
            })
        if on_progress:
            on_progress(i, len(people), person.name)

    df = pd.DataFrame(rows)
    df["ml_right"] = df.ml_says_falls == df.actually_fell
    df["twin_right"] = df.twin_says_falls == df.actually_fell
    return df


def summarise(df):
    """The headline numbers, and the two kinds of mistake."""
    return {
        "predictions": len(df),
        "ml": 100 * df.ml_right.mean(),
        "twin": 100 * df.twin_right.mean(),
        "difference": 100 * (df.ml_right.mean() - df.twin_right.mean()),
        # Under-predicting failure is the riskier error: those are people
        # the model would not have flagged for training.
        "missed": int(((~df.ml_says_falls) & df.actually_fell).sum()),
        "over": int((df.ml_says_falls & (~df.actually_fell)).sum()),
    }


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    print("Training on the logged history...")
    df = run(n, on_progress=lambda i, total, name:
             print("   %2d/%d  %s" % (i, total, name)))

    s = summarise(df)
    print()
    print("%d predictions on %d brand new emails" % (s["predictions"], n))
    print("   machine learning model     %.1f%%" % s["ml"])
    print("   counting twin  a/(a+b)     %.1f%%" % s["twin"])
    print("   difference                 %+.1f points" % s["difference"])
    print()
    print("where the ML model went wrong")
    print("   expected to catch it, but fell    %d" % s["missed"])
    print("   expected to fall, but caught it   %d" % s["over"])
    print()
    print("by awareness")
    by = df.groupby("awareness")[["ml_right", "twin_right"]].mean() * 100
    print(by.round(1).to_string())


if __name__ == "__main__":
    main()

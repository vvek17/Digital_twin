# ml_model.py
# The full machine-learning pipeline over the collected history.
#
#   1. FEATURES   turn each answer into numbers: who the person is, what the
#                 email looked like
#   2. SPLIT      hold out whole EMAILS, not random rows - otherwise the same
#                 email appears in training and testing and the score is a lie
#   3. TRAIN      three models, from simple to less simple
#   4. EVALUATE   accuracy, precision, recall, confusion matrix
#   5. COMPARE    against the counting twin, P(click) = a / (a + b)
#   6. INSPECT    which features the model actually leaned on
#
# WHAT THIS DOES AND DOES NOT SHOW
#
# The labels come from the rule reader, which decides by inspecting the email.
# So a model trained here is learning to reproduce those rules. A high score
# means the pipeline works and the rules are learnable - it is NOT evidence
# about real human behaviour, because no human generated these labels.
#
# Run with:
#     python3 ml_model.py

import collections
import json
import os
import random

import numpy as np
import pandas as pd
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (accuracy_score, classification_report,
                             confusion_matrix, roc_auc_score)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.compose import ColumnTransformer
from sklearn.tree import DecisionTreeClassifier

from persona import load_people
from twin import TwinPredictor

LOG = os.path.join("data", "history_log.jsonl")
EMAILS_JSON = os.path.join("data", "hospital_emails_mixed.json")

REAL_DOMAIN = "ashbrookgeneral.example"

CATEGORICAL = ["awareness", "workload", "shift", "role_group",
               "technique", "cue", "difficulty", "address_trick"]
NUMERIC = ["years_in_role", "body_length", "red_flag_count",
           "has_reply_to_mismatch", "has_hidden_link",
           "sender_domain_matches", "is_phishing"]


# ---------------------------------------------------------------- 1. FEATURES

def domain_of(address):
    return address.rsplit("@", 1)[1].lower() if address and "@" in address else ""


def build_dataset(log_path=LOG):
    """One row per answer: person features + email features + the label."""
    people = {p.id: p for p in load_people()}
    emails = {e["id"]: e for e in json.load(open(EMAILS_JSON))["emails"]}

    twin = TwinPredictor(log_path=None, csv_path=None, results_path=None)
    twin.rebuild_from_log(log_path)

    rows = []
    for pid, events in twin.history.items():
        person = people.get(pid)
        if not person:
            continue
        for ev in events:
            if "correct" not in ev:
                continue
            email = emails.get(ev["email_id"])
            if not email:
                continue

            phishing = email["label"] == "phishing"
            reply_to = email.get("reply_to")
            sender_domain = domain_of(email.get("sender_email", ""))

            rows.append({
                # --- who ---
                "person_id": pid,
                "awareness": person.security_awareness,
                "workload": person.workload,
                "shift": person.shift,
                "role_group": person.role_group,
                "years_in_role": person.years_in_role or 0,
                # --- what they were sent ---
                "email_id": email["id"],
                "technique": email.get("technique") or "none",
                "cue": email.get("cue") or "none",
                "difficulty": email.get("difficulty") or "unknown",
                "address_trick": email.get("address_trick") or "none",
                "is_phishing": int(phishing),
                "body_length": len(email.get("body", "")),
                "red_flag_count": len(email.get("red_flags") or []),
                "has_hidden_link": int(bool(email.get("link_target"))),
                "has_reply_to_mismatch": int(
                    bool(reply_to) and domain_of(reply_to) != sender_domain),
                "sender_domain_matches": int(sender_domain == REAL_DOMAIN),
                # --- what happened (the label) ---
                "fell_for_it": int(not ev["correct"]),
            })

    return pd.DataFrame(rows)


def featurize(person, email):
    """One feature row for a person + email pair.

    Used for brand new emails that are not in the history, so the trained
    model can score them. Must produce exactly the columns build_dataset does.
    """
    phishing = email["label"] == "phishing"
    reply_to = email.get("reply_to")
    sender_domain = domain_of(email.get("sender_email", ""))

    return {
        "awareness": person.security_awareness,
        "workload": person.workload,
        "shift": person.shift,
        "role_group": person.role_group,
        "years_in_role": person.years_in_role or 0,
        "technique": email.get("technique") or "none",
        "cue": email.get("cue") or "none",
        "difficulty": email.get("difficulty") or "unknown",
        "address_trick": email.get("address_trick") or "none",
        "is_phishing": int(phishing),
        "body_length": len(email.get("body", "")),
        "red_flag_count": len(email.get("red_flags") or []),
        "has_hidden_link": int(bool(email.get("link_target"))),
        "has_reply_to_mismatch": int(
            bool(reply_to) and domain_of(reply_to) != sender_domain),
        "sender_domain_matches": int(sender_domain == REAL_DOMAIN),
    }


def train_best(df=None, log_path=LOG):
    """Train the random forest on all available history and return it."""
    df = build_dataset(log_path) if df is None else df
    features = CATEGORICAL + NUMERIC
    model = make_models()["Random forest"]
    model.fit(df[features], df["fell_for_it"])
    return model, features


# ------------------------------------------------------------------- 2. SPLIT

def split_by_email(df, test_fraction=0.3, seed=7):
    """Hold out whole emails.

    Splitting rows at random would put the same email in both halves, and the
    model would score well by memorising that email rather than learning
    anything. Holding out emails tests what we actually care about: does it
    work on an email it has never seen?
    """
    ids = sorted(df["email_id"].unique())
    rng = random.Random(seed)
    rng.shuffle(ids)
    n_test = max(1, int(len(ids) * test_fraction))
    test_ids = set(ids[:n_test])

    train = df[~df["email_id"].isin(test_ids)]
    test = df[df["email_id"].isin(test_ids)]
    return train, test, sorted(test_ids)


# ------------------------------------------------------------------- 3. TRAIN

def make_models():
    pre = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
        ("num", StandardScaler(), NUMERIC),
    ])
    return {
        "Always majority (baseline)": Pipeline([
            ("pre", pre), ("clf", DummyClassifier(strategy="most_frequent"))]),
        "Logistic regression": Pipeline([
            ("pre", pre), ("clf", LogisticRegression(max_iter=2000))]),
        "Decision tree (depth 5)": Pipeline([
            ("pre", pre), ("clf", DecisionTreeClassifier(max_depth=5, random_state=7))]),
        "Random forest": Pipeline([
            ("pre", pre), ("clf", RandomForestClassifier(
                n_estimators=200, max_depth=10, random_state=7, n_jobs=-1))]),
    }


# ---------------------------------------------------------------- 4. EVALUATE

def evaluate_model(name, model, X_train, y_train, X_test, y_test):
    model.fit(X_train, y_train)
    pred = model.predict(X_test)

    try:
        proba = model.predict_proba(X_test)[:, 1]
        auc = roc_auc_score(y_test, proba)
    except Exception:
        auc = float("nan")

    return {
        "name": name,
        "accuracy": accuracy_score(y_test, pred),
        "auc": auc,
        "pred": pred,
        "model": model,
    }


# ----------------------------------------------------------------- 5. COMPARE

def twin_baseline(test_df, log_path=LOG):
    """The counting twin's score on the same held-out emails."""
    twin = TwinPredictor(log_path=None, csv_path=None, results_path=None)
    twin.rebuild_from_log(log_path)

    emails = {e["id"]: e for e in json.load(open(EMAILS_JSON))["emails"]}
    correct = 0
    for _, row in test_df.iterrows():
        email = emails[row["email_id"]]
        predicted_fall = twin.predict(row["person_id"], email) > 0.5
        correct += int(predicted_fall == bool(row["fell_for_it"]))
    return correct / len(test_df)


# ----------------------------------------------------------------- 6. INSPECT

def feature_importance(model, top=12):
    """Which features the forest leaned on."""
    pre = model.named_steps["pre"]
    clf = model.named_steps["clf"]
    if not hasattr(clf, "feature_importances_"):
        return []
    names = pre.get_feature_names_out()
    pairs = sorted(zip(names, clf.feature_importances_),
                   key=lambda kv: -kv[1])
    return pairs[:top]


def main():
    print("1. FEATURES")
    df = build_dataset()
    print("   %d answers, %d features" % (len(df), len(CATEGORICAL) + len(NUMERIC)))
    print("   label balance: %d fell for it, %d did not"
          % (df.fell_for_it.sum(), len(df) - df.fell_for_it.sum()))
    print()

    print("2. SPLIT (whole emails held out, never seen in training)")
    train, test, test_ids = split_by_email(df)
    print("   train: %5d answers over %d emails"
          % (len(train), train.email_id.nunique()))
    print("   test : %5d answers over %d emails  %s"
          % (len(test), test.email_id.nunique(),
             ", ".join(str(i) for i in test_ids[:6])
             + (" ..." if len(test_ids) > 6 else "")))
    print()

    features = CATEGORICAL + NUMERIC
    X_train, y_train = train[features], train["fell_for_it"]
    X_test, y_test = test[features], test["fell_for_it"]

    print("3-4. TRAIN AND EVALUATE")
    print("   %-28s %9s %8s" % ("model", "accuracy", "AUC"))
    print("   " + "-" * 48)
    results = []
    for name, model in make_models().items():
        r = evaluate_model(name, model, X_train, y_train, X_test, y_test)
        results.append(r)
        print("   %-28s %8.1f%% %8s"
              % (name, 100 * r["accuracy"],
                 "%.3f" % r["auc"] if r["auc"] == r["auc"] else "-"))
    print()

    print("5. COMPARE with the counting twin")
    base = twin_baseline(test)
    best = max(results, key=lambda r: r["accuracy"])
    print("   counting twin  P(click) = a/(a+b) : %.1f%%" % (100 * base))
    print("   best ML model  %-18s : %.1f%%" % (best["name"], 100 * best["accuracy"]))
    print("   difference                        : %+.1f points"
          % (100 * (best["accuracy"] - base)))
    print()

    print("   confusion matrix for %s" % best["name"])
    cm = confusion_matrix(y_test, best["pred"])
    print("                    predicted safe  predicted fell")
    print("   actually safe    %14d  %14d" % (cm[0][0], cm[0][1]))
    print("   actually fell    %14d  %14d" % (cm[1][0], cm[1][1]))
    print()
    print(classification_report(y_test, best["pred"],
                                target_names=["did not fall", "fell for it"],
                                digits=3))

    print("6. WHAT THE MODEL LEANED ON")
    forest = next(r for r in results if r["name"] == "Random forest")
    for name, weight in feature_importance(forest["model"]):
        print("   %-42s %.3f" % (name.replace("cat__", "").replace("num__", ""), weight))

    print()
    print("NOTE: the labels came from the rule reader, so these models are")
    print("learning to reproduce those rules. The pipeline is real; the")
    print("accuracy is not evidence about human behaviour.")


if __name__ == "__main__":
    main()

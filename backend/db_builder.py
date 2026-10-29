# db_builder.py
# Builds a NEW email - fake or real - out of the three pieces:
#
#   emails.db         supplies the genuine email to start from, chosen by
#                     query rather than at random: "a hard billing email
#                     aimed at front desk staff" is one call
#   entities.py       swaps every reference number, ward, day, time and
#                     extension in it for a fresh value, so the wording is
#                     new rather than a copy
#   modifications.py  supplies the things that make it phishy, and the red
#                     flags come out of those rather than written by hand
#
# WHY START FROM A GENUINE EMAIL
#
# A fake assembled from nothing reads like a fake. Starting from real
# hospital wording and then corrupting it is what makes it hard: the only
# difference between the fake and the real one is the thing being taught.
# Both halves come out of the same pipeline, so "always answer spam" does
# not score well.
#
# This is email_builder.py's idea, sourced from the database instead of the
# JSON. The recipes and taxonomy are imported from there rather than copied.
#
# Run with:
#     python3 db_builder.py                 one of each, shown in full
#     python3 db_builder.py 20              build 20, write data/db_emails.json
#     python3 db_builder.py 1 fake          force a fake
#     python3 db_builder.py 1 real          force a real one

import json
import os
import random
import sys

from backend import entities as ENT
from backend import modifications as M
from backend.email_builder import ADDRESS_MODS, RECIPES, TAXONOMY
from database.db import EmailDB

OUT_PATH = os.path.join("data", "db_emails.json")

REAL_KEY_DEFENSE = ("If a message feels off, verify on the Staff Portal or "
                    "call the listed extension")
FAKE_KEY_DEFENSE = "Check the sender, hover the link, verify by a known number"


class DBEmailBuilder:
    """Builds new emails from seeds held in the database."""

    def __init__(self, db=None):
        self.db = db or EmailDB()
        # Genuine emails are the raw material for both halves: a fake is a
        # real email with something done to it.
        self.seeds = self.db.real()
        if not self.seeds:
            raise ValueError("no legitimate emails in the database to build from")
        # Ids continue above whatever the database already holds, so a built
        # email can never collide with a curated one.
        self._next = max(e["id"] for e in self.db.all()) + 1

    # ------------------------------------------------------------- choosing

    def next_id(self):
        self._next += 1
        return self._next - 1

    def seed_for(self, difficulty=None, target_role=None):
        """A genuine email to start from, narrowed by whatever was asked.

        Falling back to the whole pool matters: a filter that matches
        nothing should produce a less specific email, not an exception.
        """
        found = self.db.real(difficulty=difficulty, target_role=target_role)
        return dict(random.choice(found or self.seeds))

    # -------------------------------------------------------------- the two

    def build_real(self, seed=None, new_id=None, difficulty=None,
                   target_role=None):
        """A new GENUINE email: fresh entities, nothing done to it."""
        seed = seed or self.seed_for(difficulty, target_role)
        subject_t, body_t, slots = ENT.templatize(seed)
        subject, body, used = ENT.refill(subject_t, body_t, slots)

        return {
            "id": new_id if new_id is not None else self.next_id(),
            "label": "legitimate",
            "cue": "none",
            "technique": None,
            "technique_category": None,
            "table_row": None,
            "week": None,
            "cia_hit": None,
            "address_trick": None,
            "key_defense": REAL_KEY_DEFENSE,
            # An asked-for role or difficulty is what the email IS, not just
            # how its seed was chosen - the database matches 'all' as well as
            # the role, so the seed alone would not carry the request through.
            "target_role": target_role or seed.get("target_role") or "all",
            "difficulty": difficulty or seed.get("difficulty") or "easy",
            "sender_name": seed.get("sender_name") or "Notifications",
            # Genuine mail comes from the hospital's own domain, untouched.
            "sender_email": seed.get("sender_email") or "",
            "reply_to": None,
            "subject": subject,
            "body": body,
            "link_text": seed.get("link_text"),
            "link_target": seed.get("link_target"),
            "built_from": seed["id"],
            "modifications": [],
            "entities_used": used,
            "red_flags": [],
        }

    def build_fake(self, technique=None, seed=None, n_may=2, new_id=None,
                   cue=None, difficulty=None, target_role=None):
        """A new PHISHING email: fresh entities, then the modifications."""
        technique = technique or random.choice(sorted(RECIPES))
        if technique not in RECIPES:
            raise ValueError("unknown technique %r" % technique)
        recipe = RECIPES[technique]
        seed = seed or self.seed_for(difficulty, target_role)

        # Reword first, corrupt second. Doing it the other way round would
        # let refill() overwrite the values a modification just planted.
        subject_t, body_t, slots = ENT.templatize(seed)
        subject, body, used = ENT.refill(subject_t, body_t, slots)
        seed = dict(seed, subject=subject, body=body)

        names = list(recipe["must"])
        extra = [m for m in recipe["may"] if m not in names]
        names += random.sample(extra, min(n_may, len(extra)))

        # Every phishing email needs something wrong with the sender.
        if not any(n in ADDRESS_MODS for n in names):
            names.append(random.choice(sorted(ADDRESS_MODS)))

        built, flags = M.apply_all(seed, names)
        row, week, cia, category = TAXONOMY[technique]

        return {
            "id": new_id if new_id is not None else self.next_id(),
            "label": "phishing",
            "cue": cue or random.choice(recipe["cue"]),
            "technique": technique,
            "technique_category": category,
            "table_row": row,
            "week": week,
            "cia_hit": cia,
            "address_trick": next((n for n in names if n in ADDRESS_MODS), None),
            "key_defense": FAKE_KEY_DEFENSE,
            "target_role": target_role or seed.get("target_role") or "all",
            # Fewer tells is harder to spot, not easier - but only when the
            # caller did not say which difficulty they wanted.
            "difficulty": difficulty or ("hard" if len(names) <= 4 else "easy"),
            "sender_name": seed.get("sender_name") or "Notifications",
            "sender_email": built["sender_email"],
            "reply_to": built.get("reply_to"),
            "subject": built.get("subject", subject),
            "body": built["body"],
            "link_text": built.get("link_text"),
            "link_target": built.get("link_target"),
            "built_from": seed["id"],
            "modifications": names,
            "entities_used": used,
            "red_flags": flags,
        }

    # --------------------------------------------------------------- either

    def build(self, label=None, fake_ratio=0.5, **kw):
        """One email. label "phishing" or "legitimate" forces it; None rolls."""
        if label is None:
            label = "phishing" if random.random() < fake_ratio else "legitimate"
        if label == "phishing":
            return self.build_fake(**kw)
        # The attack-only arguments mean nothing on a genuine email.
        for only_fake in ("technique", "n_may", "cue"):
            kw.pop(only_fake, None)
        return self.build_real(**kw)

    def build_many(self, count, fake_ratio=0.5, **kw):
        """Several, with the fake/real mix held to the ratio rather than
        left to chance - 20 rolls of a coin can come up 15 heads."""
        n_fake = round(count * fake_ratio)
        out = [self.build(label="phishing", **kw) for _ in range(n_fake)]
        out += [self.build(label="legitimate", **kw) for _ in range(count - n_fake)]
        random.shuffle(out)
        return out

    def close(self):
        self.db.close()


def write(emails, path=OUT_PATH):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump({
            "note": ("Emails built by db_builder.py from seeds in emails.db, "
                     "plus fresh entities and modifications. Fictional, "
                     ".example domains only."),
            "count": len(emails),
            "emails": emails,
        }, f, indent=2)
        f.write("\n")
    return path


def show(e):
    print("=" * 72)
    print("%-4s %-11s %s" % (e["id"], e["label"].upper(),
                             e["technique"] or "genuine - nothing done to it"))
    print("built from %s   entities swapped: %d"
          % (e["built_from"], len(e["entities_used"])))
    if e["modifications"]:
        print("modifications: %s" % ", ".join(e["modifications"]))
    print("-" * 72)
    print("From    : %s <%s>" % (e["sender_name"], e["sender_email"]))
    if e["reply_to"]:
        print("Reply-To: %s" % e["reply_to"])
    print("Subject : %s" % e["subject"])
    print()
    print(e["body"][:420])
    print()
    if e["red_flags"]:
        print("red flags (%d):" % len(e["red_flags"]))
        for f in e["red_flags"]:
            print("   - %s" % f)
    else:
        print("red flags: none - this one is genuine")
    print()


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    count = int(args[0]) if args else 2
    forced = None
    if len(args) > 1:
        forced = {"fake": "phishing", "phishing": "phishing",
                  "real": "legitimate", "legitimate": "legitimate"}.get(args[1])
        if forced is None:
            sys.exit("second argument must be fake or real")

    builder = DBEmailBuilder()
    print("%d emails in the database, %d genuine ones to build from"
          % (len(builder.db.all()), len(builder.seeds)))
    print("%d modifications available, %d entity kinds\n" % (len(M.ALL), len(ENT.ALL)))

    if forced:
        built = [builder.build(label=forced) for _ in range(count)]
    elif count <= 2:
        # The default: one of each, so the pair can be compared side by side.
        built = [builder.build(label="phishing"), builder.build(label="legitimate")]
    else:
        built = builder.build_many(count)

    if count > 5:
        path = write(built)
        fakes = sum(1 for e in built if e["label"] == "phishing")
        print("Built %d emails -> %s" % (len(built), path))
        print("   %d fake, %d real" % (fakes, len(built) - fakes))
        ids = [e["id"] for e in built]
        print("   ids %d..%d" % (min(ids), max(ids)))
    else:
        for e in built:
            show(e)

    builder.close()


if __name__ == "__main__":
    main()

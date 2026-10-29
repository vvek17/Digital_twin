# email_generator.py
# Generates a NEW email on demand, never returning a static one as-is.
#
# Three stages, each from a module of its own:
#
#   1. entities.py        a static email becomes a template, and the slots
#                         are refilled with fresh values - new reference
#                         numbers, days, times, wards, extensions
#   2. modifications.py   the phishy parts are applied - forged sender,
#                         hidden link, urgency, misspelling, and the rest
#   3. this file          checks the result is not too close to anything
#                         already produced, then appends it to the CSV
#
# ON "A GENERATIVE MODEL"
#
# The spec asks for a generative model. This implementation is template and
# entity driven, which needs no API key and runs offline. The seam for a
# language model is one function - generate_body() - so swapping one in later
# changes this file only. What a model would add is fresh WORDING; what is
# here already varies structure, entity values and email type.
#
# DUPLICATE CHECK
#
# Similarity is measured on the subject and body together with difflib. A new
# email scoring above SIMILARITY_LIMIT against anything already generated is
# thrown away and rebuilt, up to MAX_TRIES times.
#
# Run with:
#     python3 email_generator.py          generate one
#     python3 email_generator.py 20       generate twenty

import csv
import json
import os
import random
import sys
from datetime import datetime
from difflib import SequenceMatcher

from backend import entities as ENT
from backend import modifications as MODS
from backend.email_builder import RECIPES, TAXONOMY, ADDRESS_MODS

OUT_CSV = os.path.join("data", "generated_emails.csv")

# Email ids are one integer sequence. The curated set in
# data/hospital_emails_mixed.json holds the low numbers; everything built
# here carries on above them, so no generated email can shadow a curated one.
CURATED_MAX = 51

CSV_COLUMNS = ["ID", "Timestamp", "Email Type", "Subject", "Body",
               "Entities Used", "Modifications", "Built From", "Red Flags"]

# Above this, two emails count as the same thing reworded.
SIMILARITY_LIMIT = 0.80
MAX_TRIES = 12


def similarity(a, b):
    """0 to 1. Compares subject and body together."""
    return SequenceMatcher(None, a, b).ratio()


def fingerprint(email):
    return "%s\n%s" % (email.get("subject", ""), email.get("body", ""))


class EmailGeneratorLLM:
    """Generates new emails from the static ones without copying them."""

    def __init__(self, static=None, csv_path=OUT_CSV):
        self.static = static or ENT.load_static()
        # Genuine emails are the raw material: real structure, real wording.
        self.bases = [e for e in self.static if e["label"] == "legitimate"]
        self.csv_path = csv_path
        self.seen = self._load_fingerprints()

    # ------------------------------------------------------------ the CSV

    def _load_fingerprints(self):
        """What has already been generated, so we can avoid repeating it."""
        out = []
        if not os.path.exists(self.csv_path):
            return out
        with open(self.csv_path) as f:
            for row in csv.DictReader(f):
                out.append("%s\n%s" % (row.get("Subject", ""), row.get("Body", "")))
        return out

    def next_id(self):
        return CURATED_MAX + len(self.seen) + 1

    def append(self, email):
        new_file = not os.path.exists(self.csv_path)
        os.makedirs(os.path.dirname(self.csv_path) or ".", exist_ok=True)
        with open(self.csv_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS,
                                    extrasaction="ignore")
            if new_file:
                writer.writeheader()
            writer.writerow({
                "ID": email["id"],
                "Timestamp": email["timestamp"],
                "Email Type": email["technique"],
                "Subject": email["subject"],
                "Body": email["body"],
                "Entities Used": json.dumps(email["entities_used"]),
                "Modifications": ", ".join(email["modifications"]),
                "Built From": email["built_from"],
                "Red Flags": " | ".join(email["red_flags"]),
            })
            f.flush()
            os.fsync(f.fileno())
        self.seen.append(fingerprint(email))

    # ------------------------------------------------------- the generation

    def generate_body(self, base):
        """Produce fresh subject and body text from a static email.

        THIS IS THE SEAM. Right now it turns the email into a template and
        refills every slot with a new value of the same shape. To use a
        language model instead, replace the inside of this function - pass
        the base email and its entities as context, ask for a new message in
        the same style, and return (subject, body, entities_used). Nothing
        else in the file changes.
        """
        subject_t, body_t, slots = ENT.templatize(base)
        return ENT.refill(subject_t, body_t, slots)

    def generate_legitimate(self):
        """A new GENUINE email: fresh entity values, nothing done to it."""
        base = random.choice(self.bases)
        subject, body, entities_used = self.generate_body(base)
        return {
            "id": self.next_id(),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "label": "legitimate",
            "technique": "Legitimate",
            "cue": "none",
            "address_trick": None,
            "difficulty": base.get("difficulty", "easy"),
            "target_role": base.get("target_role", "all"),
            "key_defense": "Verify on the Staff Portal or call the listed extension",
            "sender_name": base.get("sender_name", "Notifications"),
            "sender_email": base.get("sender_email", ""),
            "reply_to": None,
            "subject": subject,
            "body": body,
            "link_text": None,
            "link_target": None,
            "built_from": base["id"],
            "modifications": [],
            "entities_used": entities_used,
            "red_flags": [],
        }

    def generate_once(self, technique=None, fake=True):
        """Build one candidate, without checking it for similarity."""
        if not fake:
            return self.generate_legitimate()
        technique = technique or random.choice(list(RECIPES))
        recipe = RECIPES[technique]
        base = random.choice(self.bases)

        subject, body, entities_used = self.generate_body(base)

        # Start from the refilled text, then make it phishy.
        draft = dict(base)
        draft["subject"] = subject
        draft["body"] = body

        names = list(recipe["must"])
        extra = [m for m in recipe["may"] if m not in names]
        names += random.sample(extra, min(2, len(extra)))
        if not any(n in ADDRESS_MODS for n in names):
            names.append(random.choice(sorted(ADDRESS_MODS)))

        built, flags = MODS.apply_all(draft, names)
        row, week, cia, category = TAXONOMY[technique]

        return {
            "id": self.next_id(),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "label": "phishing",
            "technique": technique,
            "technique_category": category,
            "table_row": row,
            "week": week,
            "cia_hit": cia,
            "cue": random.choice(recipe["cue"]),
            "address_trick": next((n for n in names if n in ADDRESS_MODS), None),
            "difficulty": "hard" if len(names) <= 4 else "easy",
            "target_role": base.get("target_role", "all"),
            "key_defense": "Check the sender, hover the link, verify by a known number",
            "sender_name": base.get("sender_name", "Notifications"),
            "sender_email": built["sender_email"],
            "reply_to": built.get("reply_to"),
            "subject": built.get("subject", subject),
            "body": built["body"],
            "link_text": built.get("link_text"),
            "link_target": built.get("link_target"),
            "built_from": base["id"],
            "modifications": names,
            "entities_used": entities_used,
            "red_flags": flags,
        }

    def too_similar(self, candidate):
        """True if this is close to something already generated, or to a static one."""
        fp = fingerprint(candidate)
        for existing in self.seen:
            if similarity(fp, existing) > SIMILARITY_LIMIT:
                return True
        # A static email must never come back unchanged.
        for static in self.static:
            if similarity(fp, fingerprint(static)) > SIMILARITY_LIMIT:
                return True
        return False

    def generate(self, technique=None, save=True, fake=True):
        """Generate one new email that is not too close to anything seen."""
        for attempt in range(MAX_TRIES):
            candidate = self.generate_once(technique, fake=fake)
            if not self.too_similar(candidate):
                candidate["attempts"] = attempt + 1
                if save:
                    self.append(candidate)
                return candidate
        # Everything was too close - say so rather than saving a duplicate.
        return None

    def generate_many(self, count, save=True, fake_ratio=0.5):
        """Several, mixed fake and genuine - a set of only fakes is not a test."""
        out, rejected = [], 0
        for n in range(count):
            email = self.generate(save=save, fake=random.random() < fake_ratio)
            if email:
                out.append(email)
            else:
                rejected += 1
        return out, rejected


if __name__ == "__main__":
    random.seed()
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    gen = EmailGeneratorLLM()

    print("already generated: %d\n" % len(gen.seen))
    made, rejected = gen.generate_many(count)
    print("generated %d, rejected %d as too similar -> %s\n"
          % (len(made), rejected, OUT_CSV))

    for e in made[:3]:
        print("=" * 72)
        print("%s  %s   (built from %s, %d attempt(s))"
              % (e["id"], e["technique"], e["built_from"], e["attempts"]))
        print("From   :", e["sender_email"])
        if e["reply_to"]:
            print("Reply-To:", e["reply_to"])
        print("Subject:", e["subject"])
        print("-" * 72)
        print(e["body"][:340])
        print()
        print("entities used :", json.dumps(e["entities_used"]))
        print("modifications :", ", ".join(e["modifications"]))
        print()

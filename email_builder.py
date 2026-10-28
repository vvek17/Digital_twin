# email_builder.py
# Builds NEW emails from the two modules:
#
#   generator.py      supplies a genuine email to start from
#   modifications.py  supplies the things that make it phishy
#
# A technique decides which modifications are plausible for it. Whaling needs
# authority and secrecy; malware needs an attachment; smishing pushes you to
# a text message. So each technique names the modifications it must have and
# the ones it may have, and the builder picks from those.
#
# The result is a complete email in the same shape as the 51 originals -
# including red_flags, which are produced by the modifications rather than
# written by hand.
#
# Run with:
#     python3 email_builder.py            build a few and show them
#     python3 email_builder.py 200        build 200 and write data/new_emails.json

import json
import os
import random
import sys

from generator import EmailGenerator
import modifications as M
import entities as ENT

OUT_PATH = os.path.join("data", "new_emails.json")

# Which modifications each technique needs, and which it may add.
# "must" are what make it that technique; "may" is the variation.
RECIPES = {
    "Phishing": {
        "cue": ["it_login", "urgency", "billing", "hr_payroll"],
        "must": ["hidden_link", "credential_request"],
        "may": ["lookalike", "typosquat", "extra_ending", "urgency",
                "generic_greeting", "reply_to_mismatch", "misspelling"],
    },
    "Spear phishing": {
        "cue": ["authority", "hr_payroll", "urgency"],
        "must": ["hidden_link"],
        "may": ["forged_from", "free_provider", "reply_to_mismatch",
                "urgency", "pressure"],
    },
    "Whaling": {
        "cue": ["authority"],
        "must": ["pressure", "credential_request"],
        "may": ["typosquat", "forged_from", "urgency", "no_contact"],
    },
    "Pretexting": {
        "cue": ["authority", "billing", "urgency"],
        "must": ["credential_request"],
        "may": ["unrelated", "extra_ending", "urgency", "generic_greeting"],
    },
    "Baiting": {
        "cue": ["hr_payroll"],
        "must": ["dangerous_attachment"],
        "may": ["lookalike", "free_provider", "pressure", "generic_greeting"],
    },
    "Malware": {
        "cue": ["urgency", "billing"],
        "must": ["dangerous_attachment"],
        "may": ["lookalike", "urgency", "misspelling", "no_contact"],
    },
    "Ransomware": {
        "cue": ["billing"],
        "must": ["dangerous_attachment", "pressure"],
        "may": ["lookalike", "extra_ending", "misspelling"],
    },
    "Quid pro quo": {
        "cue": ["it_login"],
        "must": ["credential_request", "hidden_link"],
        "may": ["lookalike", "generic_greeting", "urgency"],
    },
    "Smishing": {
        "cue": ["hr_payroll"],
        "must": ["hidden_link", "urgency"],
        "may": ["lookalike", "no_contact", "generic_greeting"],
    },
    "Extortion / blackmail": {
        "cue": ["urgency"],
        "must": ["pressure", "hidden_link"],
        "may": ["unrelated", "no_contact", "generic_greeting", "misspelling"],
    },
    "Third-party / supply chain": {
        "cue": ["billing", "it_login"],
        "must": ["hidden_link"],
        "may": ["unrelated", "forged_from", "reply_to_mismatch", "urgency"],
    },
}

# The taxonomy fields that go with each technique, so a built email carries
# the same tags as the originals.
TAXONOMY = {
    "Phishing": (10, 7, "C", "Social engineering (email/web)"),
    "Spear phishing": (11, 7, "C", "Social engineering (targeted)"),
    "Whaling": (12, 7, "C", "Social engineering (executives)"),
    "Pretexting": (13, 7, "C", "Social engineering (false story)"),
    "Baiting": (14, 7, "I + C", "Social engineering (temptation)"),
    "Malware": (1, 7, "C, I, A", "Technical (malicious software)"),
    "Ransomware": (2, 7, "A", "Technical (malware type)"),
    "Quid pro quo": (18, 8, "C", "Social engineering (trade)"),
    "Smishing": (17, 7, "C", "Social engineering (text message)"),
    "Extortion / blackmail": (20, 8, "C", "Social engineering (threat)"),
    "Third-party / supply chain": (9, 7, "C + A", "Organizational risk"),
}

ADDRESS_MODS = {m.name for m in M.family("address")}


class EmailBuilder:
    def __init__(self, generator=None):
        self.gen = generator or EmailGenerator()
        # Genuine emails are the raw material - real subjects, real wording.
        self.bases = self.gen.real()

    def build_legitimate(self, base=None, new_id=None):
        """Build a new GENUINE email.

        Same first step as a fake - start from a real email and swap every
        entity for a fresh value - but no modifications are applied. The
        result is new wording with nothing wrong with it, which is what a
        balanced set needs. Without these, every dynamic email is phishing
        and "always answer spam" scores perfectly.
        """
        base = base or random.choice(self.bases)
        subject_t, body_t, slots = ENT.templatize(base)
        subject, body, entities_used = ENT.refill(subject_t, body_t, slots)

        return {
            "id": new_id or "L%03d" % random.randint(1, 999),
            "label": "legitimate",
            "cue": "none",
            "technique": None,
            "technique_category": None,
            "table_row": None,
            "week": None,
            "cia_hit": None,
            "address_trick": None,
            "key_defense": ("If a message feels off, verify on the Staff Portal "
                            "or call the listed extension"),
            "target_role": base.get("target_role", "all"),
            "difficulty": base.get("difficulty", "easy"),
            "sender_name": base.get("sender_name", "Notifications"),
            # Genuine mail comes from the hospital's own domain, untouched.
            "sender_email": base.get("sender_email", ""),
            "reply_to": None,
            "subject": subject,
            "body": body,
            "link_text": None,
            "link_target": None,
            "built_from": base["id"],
            "modifications": [],
            "entities_used": entities_used,
            "safe_signs": list(base.get("safe_signs") or []),
            "red_flags": [],
        }

    def build_any(self, fake_ratio=0.5, new_id=None):
        """One email, fake or genuine, according to the ratio."""
        if random.random() < fake_ratio:
            return self.build_one(new_id=new_id)
        return self.build_legitimate(new_id=new_id)

    def build_one(self, technique=None, base=None, n_may=2, new_id=None):
        """Build one new phishing email."""
        technique = technique or random.choice(list(RECIPES))
        recipe = RECIPES[technique]
        base = base or random.choice(self.bases)

        names = list(recipe["must"])
        extra = [m for m in recipe["may"] if m not in names]
        names += random.sample(extra, min(n_may, len(extra)))

        # Every phishing email needs something wrong with the sender. If the
        # recipe did not pick an address trick, add one.
        if not any(n in ADDRESS_MODS for n in names):
            names.append(random.choice(sorted(ADDRESS_MODS)))

        built, flags = M.apply_all(base, names)
        row, week, cia, category = TAXONOMY[technique]
        address_trick = next((n for n in names if n in ADDRESS_MODS), None)

        return {
            "id": new_id or "N%03d" % random.randint(1, 999),
            "label": "phishing",
            "cue": random.choice(recipe["cue"]),
            "technique": technique,
            "technique_category": category,
            "table_row": row,
            "week": week,
            "cia_hit": cia,
            "address_trick": address_trick,
            "key_defense": "Check the sender, hover the link, verify by a known number",
            "target_role": base.get("target_role", "all"),
            # Built emails are "hard" by default: they are assembled from the
            # same parts as the originals, with no deliberate giveaway.
            "difficulty": "hard" if len(names) <= 4 else "easy",
            "sender_name": base.get("sender_name", "Notifications"),
            "sender_email": built["sender_email"],
            "reply_to": built.get("reply_to"),
            "subject": built.get("subject", base["subject"]),
            "body": built["body"],
            "link_text": built.get("link_text"),
            "link_target": built.get("link_target"),
            "built_from": base["id"],
            "modifications": names,
            "red_flags": flags,
        }

    def build(self, count, techniques=None, fake_ratio=0.5):
        """Build several: phishing spread across techniques, plus genuine ones.

        fake_ratio sets the mix. The default 0.5 matches the curated set,
        which is 26 fake and 25 real.
        """
        techniques = techniques or list(RECIPES)
        n_fake = round(count * fake_ratio)
        out = []
        for n in range(count):
            new_id = "N%03d" % (n + 1)
            if n < n_fake:
                out.append(self.build_one(techniques[n % len(techniques)],
                                          new_id=new_id))
            else:
                out.append(self.build_legitimate(new_id=new_id))
        random.shuffle(out)
        return out


def write(emails, path=OUT_PATH):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump({
            "note": ("Emails built by email_builder.py from genuine emails plus "
                     "modifications. Fictional, .example domains only."),
            "count": len(emails),
            "emails": emails,
        }, f, indent=2)
        f.write("\n")
    return path


if __name__ == "__main__":
    random.seed(11)
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    builder = EmailBuilder()
    built = builder.build(count)

    if count > 5:
        path = write(built)
        print("Built %d emails -> %s\n" % (len(built), path))
        import collections
        for name, n in collections.Counter(e["technique"] for e in built).most_common():
            print("   %-28s %d" % (name, n))
    else:
        for e in built:
            print("=" * 72)
            print("%s  %s" % (e["id"], e["technique"]))
            print("built from %s, modifications: %s"
                  % (e["built_from"], ", ".join(e["modifications"])))
            print("-" * 72)
            print("From    :", e["sender_email"])
            if e["reply_to"]:
                print("Reply-To:", e["reply_to"])
            print("Subject :", e["subject"])
            print()
            print(e["body"][:380])
            print()
            print("red flags:")
            for f in e["red_flags"]:
                print("   -", f)
            print()

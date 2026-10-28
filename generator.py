# generator.py
# Decides WHICH email a person gets next.
#
# The emails themselves live in the database (email_db.py). This module is
# only about selection, and it offers several strategies because the right
# one depends on what you are doing:
#
#   random      any email, repeats allowed       - volume over time
#   unseen      only what they have not judged   - a clean one-shot test
#   balanced    alternate fake and real          - keeps the mix even
#   targeted    only what is aimed at their role - realistic delivery
#
# It still reads the JSON through the DB builder, so nothing else has to
# change: .emails is the same list of dicts the old version exposed.

import random

from email_db import EmailDB


class EmailGenerator:
    def __init__(self, db=None, db_path=None):
        self.db = db or (EmailDB(db_path) if db_path else EmailDB())
        # Kept so existing callers that read .emails still work.
        self.emails = self.db.all()
        self.by_id = {e["id"]: e for e in self.emails}

    # ------------------------------------------------------------ strategies

    def get_email(self, role=None):
        """Any email, repeats allowed."""
        options = self.db.find(target_role=role) if role else self.emails
        return random.choice(options) if options else None

    def get_unseen(self, seen_ids, role=None):
        """An email this person has not judged yet, or None when done."""
        options = self.db.find(target_role=role, exclude_ids=list(seen_ids or []))
        return random.choice(options) if options else None

    def get_balanced(self, seen_ids=None, want_fake=None, role=None):
        """Keep the fake/real mix even rather than leaving it to chance.

        want_fake True forces a fake, False forces a real one, None picks
        whichever the person has seen less of.
        """
        seen_ids = set(seen_ids or [])

        if want_fake is None:
            seen_fake = sum(1 for i in seen_ids
                            if self.by_id.get(i, {}).get("is_fake"))
            seen_real = len(seen_ids) - seen_fake
            want_fake = seen_fake <= seen_real

        label = "phishing" if want_fake else "legitimate"
        options = self.db.find(label=label, target_role=role,
                               exclude_ids=list(seen_ids))
        if not options:
            # Run out of that kind - fall back to anything unseen.
            options = self.db.find(target_role=role, exclude_ids=list(seen_ids))
        return random.choice(options) if options else None

    def get_targeted(self, person, seen_ids=None, allow_repeats=True):
        """What this person would realistically receive, by their role."""
        role = getattr(person, "role_group", None)
        if allow_repeats:
            return self.get_email(role=role)
        return self.get_unseen(seen_ids or set(), role=role)

    # --------------------------------------------------------------- lookups

    def get_by_id(self, email_id):
        return self.by_id.get(email_id)

    def fakes(self, **kw):
        return self.db.fakes(**kw)

    def real(self, **kw):
        return self.db.real(**kw)

    def count(self, **kw):
        return self.db.count(**kw)

    def __len__(self):
        return len(self.emails)


if __name__ == "__main__":
    gen = EmailGenerator()
    print("%d emails: %d fake, %d real\n"
          % (len(gen), gen.count(label="phishing"), gen.count(label="legitimate")))

    print("random          :", gen.get_email()["id"])
    print("unseen (E01-E10):", gen.get_unseen({"E%02d" % i for i in range(1, 11)})["id"])
    print("balanced, want a fake:", gen.get_balanced(want_fake=True)["id"])
    print("balanced, want a real:", gen.get_balanced(want_fake=False)["id"])
    print()

    print("balanced over 10 draws for one person:")
    seen = set()
    for _ in range(10):
        e = gen.get_balanced(seen)
        seen.add(e["id"])
        print("   %-5s %-10s %s" % (e["id"], e["label"], e["subject"][:44]))

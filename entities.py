# entities.py
# Pulls the changeable values out of the static emails, so a new email can be
# written with different ones instead of reusing the same text.
#
# An email is mostly fixed wording with a few slots in it:
#
#     "Change reference CHG-2291. No sign-in is required."
#                       ^^^^^^^^ a slot
#     "A scheduled fire drill will take place on Thursday at 10 AM."
#                                                ^^^^^^^^    ^^^^^ slots
#
# Finding those slots turns one email into a template that can produce many.
# Each entity type becomes its own small module: a pattern that recognises it,
# and a maker that invents a fresh value of the same shape.
#
# Nothing here calls an outside model. The makers produce values of the right
# SHAPE (a ticket that looks like a ticket, a time that looks like a time),
# which is what a template needs.
#
# Run with:
#     python3 entities.py          show what it finds across the 51 emails

import json
import os
import random
import re

SOURCE = os.path.join("data", "hospital_emails_mixed.json")

# Vocabulary the makers draw on. Hospital-flavoured, all fictional.
WARDS = ["Ward 4", "Ward 7", "Ward 2", "Ward 9", "Theatre 3"]
PLACES = ["Lot A", "Lot B", "Lot C", "Level 1", "Level 2", "Level 3"]
DEPARTMENTS = ["Pharmacy", "Radiology", "Pathology", "Human Resources",
               "Finance & Billing", "Patient Access", "Facilities",
               "Occupational Health", "Medical Staffing"]
# No leading "the" - the surrounding sentence already supplies it.
SYSTEMS = ["Staff Portal", "records system", "rota system",
           "finance system", "booking system", "learning portal"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
        "Saturday", "Sunday"]
MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]
ACTIONS = ["review", "confirm", "acknowledge", "complete", "approve",
           "verify", "submit"]
TONES = ["routine", "urgent", "formal", "friendly", "procedural"]


class Entity:
    """One kind of changeable value."""

    name = "entity"
    pattern = None          # how to recognise it in existing text
    description = ""

    def find(self, text):
        """Every occurrence of this entity in a piece of text."""
        if not self.pattern:
            return []
        return [m.group(0) for m in re.finditer(self.pattern, text)]

    def make(self):
        """Invent a fresh value of the same shape."""
        raise NotImplementedError

    def __repr__(self):
        return "<entity %s>" % self.name


class TicketRef(Entity):
    name = "ticket_ref"
    description = "Change, incident, purchase order or invoice reference."
    pattern = r"\b(?:CHG|INC|PO|ASH)[-\s]?\d{3,5}\b|\binvoice #\d+\b"

    def make(self):
        kind = random.choice(["CHG", "INC", "PO", "ASH"])
        return "%s-%d" % (kind, random.randint(1000, 9999))


class Extension(Entity):
    name = "extension"
    description = "An internal phone extension."
    pattern = r"\bextension \d{3,4}\b"

    def make(self):
        return "extension %d" % random.randint(4100, 4499)


class DayName(Entity):
    name = "day"
    description = "A day of the week."
    pattern = r"\b(?:Mon|Tues|Wednes|Thurs|Fri|Satur|Sun)day\b"

    def make(self):
        return random.choice(DAYS)


class DateValue(Entity):
    name = "date"
    description = "A calendar date."
    pattern = (r"\b(?:January|February|March|April|May|June|July|August|"
               r"September|October|November|December)\s+\d{1,2}\b")

    def make(self):
        return "%s %d" % (random.choice(MONTHS), random.randint(1, 28))


class TimeValue(Entity):
    name = "time"
    description = "A clock time or a window."
    pattern = r"\b\d{1,2}(?:-\d{1,2})?\s*(?:AM|PM)\b"

    def make(self):
        hour = random.randint(1, 12)
        half = random.choice(["AM", "PM"])
        if random.random() < 0.3:
            return "%d-%d %s" % (hour, min(hour + 2, 12), half)
        return "%d %s" % (hour, half)


class Duration(Entity):
    name = "duration"
    description = "How long something lasts, or a deadline window."
    pattern = r"\b\d+\s*(?:hours?|minutes?|days?|weeks?)\b"

    def make(self):
        n, unit = random.choice([(24, "hours"), (48, "hours"), (30, "minutes"),
                                 (2, "days"), (3, "working days"),
                                 (20, "minutes"), (1, "hour")])
        return "%d %s" % (n, unit)


class Ward(Entity):
    name = "ward"
    description = "A ward, unit or theatre."
    pattern = r"\bWard \d+\b|\bTheatre \d\b"

    def make(self):
        return random.choice(WARDS)


class Place(Entity):
    name = "place"
    description = "A car park or floor - somewhere in the building, not a ward."
    pattern = r"\bLot [A-C]\b|\bLevel \d\b"

    def make(self):
        return random.choice(PLACES)


class Department(Entity):
    name = "department"
    description = "A hospital department."
    pattern = r"\b(?:Pharmacy|Radiology|Laboratory|Human Resources|Scheduling|Facilities|Catering|Payroll)\b"

    def make(self):
        return random.choice(DEPARTMENTS)


class SystemName(Entity):
    name = "system"
    description = "The system the email talks about."
    pattern = r"\bStaff Portal\b|\brecords system\b|\brota system\b|\bfinance system\b"

    def make(self):
        return random.choice(SYSTEMS)


class Percentage(Entity):
    name = "percentage"
    description = "A figure quoted in the message."
    pattern = r"\b\d{1,3}%"

    def make(self):
        return "%d%%" % random.randint(5, 99)


class CallToAction(Entity):
    name = "call_to_action"
    description = "What the reader is asked to do."
    pattern = r"\b(?:review|confirm|acknowledge|complete|approve|verify|submit)\b"

    def make(self):
        return random.choice(ACTIONS)


# Entities with no pattern: they describe the email rather than appear in it.
class Tone(Entity):
    name = "tone"
    description = "How the message reads. Not found in the text, chosen for it."

    def make(self):
        return random.choice(TONES)


ALL = [TicketRef(), Extension(), DayName(), DateValue(), TimeValue(),
       Duration(), Ward(), Place(), Department(), SystemName(),
       Percentage(), CallToAction(), Tone()]

BY_NAME = {e.name: e for e in ALL}


# ------------------------------------------------------------- extraction

def extract(email):
    """Every entity found in one email, as {entity_name: [values]}."""
    text = "%s\n%s" % (email.get("subject", ""), email.get("body", ""))
    found = {}
    for entity in ALL:
        values = entity.find(text)
        if values:
            # Keep order, drop repeats.
            found[entity.name] = list(dict.fromkeys(values))
    return found


def templatize(email):
    """Replace the entities in an email with named slots.

    Returns (template subject, template body, slots found). The template can
    then be refilled with fresh values, which is what makes a new email
    rather than a copy.
    """
    subject = email.get("subject", "")
    body = email.get("body", "")
    slots = {}

    for entity in ALL:
        if not entity.pattern:
            continue
        for n, value in enumerate(dict.fromkeys(entity.find(subject + "\n" + body))):
            key = entity.name if n == 0 else "%s_%d" % (entity.name, n + 1)
            token = "{%s}" % key
            slots[key] = value
            subject = subject.replace(value, token)
            body = body.replace(value, token)

    return subject, body, slots


def refill(subject, body, slots):
    """Fill a template with fresh values of the same shape."""
    used = {}
    # Slots of the same kind (day, day_2) should get different values -
    # "from Sunday to Sunday" reads as a mistake.
    taken = {}
    for key in slots:
        base = key.rsplit("_", 1)[0] if key[-1].isdigit() else key
        entity = BY_NAME.get(base)
        if not entity:
            used[key] = slots[key]
            continue
        already = taken.setdefault(base, set())
        for _ in range(12):
            value = entity.make()
            if value not in already:
                break
        already.add(value)
        used[key] = value

    for key, value in used.items():
        token = "{%s}" % key
        subject = subject.replace(token, value)
        body = body.replace(token, value)
    return subject, body, used


def load_static(path=SOURCE):
    with open(path) as f:
        return json.load(f)["emails"]


if __name__ == "__main__":
    emails = load_static()

    print("%d entity types\n" % len(ALL))
    for e in ALL:
        print("   %-16s %s" % (e.name, e.description))
    print()

    import collections
    counts = collections.Counter()
    for email in emails:
        for name in extract(email):
            counts[name] += 1
    print("found across the %d static emails:" % len(emails))
    for name, n in counts.most_common():
        print("   %-16s in %2d emails" % (name, n))
    print()

    sample = next(e for e in emails if e["id"] == 38)
    subject, body, slots = templatize(sample)
    print("=" * 70)
    print("TEMPLATE from %s" % sample["id"])
    print("=" * 70)
    print(subject)
    print(body[:280])
    print()
    print("slots:", slots)
    print()
    new_subject, new_body, used = refill(subject, body, slots)
    print("=" * 70)
    print("REFILLED with fresh values")
    print("=" * 70)
    print(new_subject)
    print(new_body[:280])
    print()
    print("used:", used)

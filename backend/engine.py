# engine.py
# One delivery: an email arrives at a person and they do something with it.
#
# The Live tab and the Run tab are the same loop at different speeds - Live
# shows each arrival, Run does a thousand silently. They used to hold two
# copies of this code, which is how they drifted apart. Both now call in
# here, so a change to how a delivery works happens once.
#
# Nothing in this file imports streamlit. That is the point: the loop can be
# run from a script, a test, or the UI, and it behaves the same.
#
# A delivery is always the same four steps, in this order:
#
#   1. pick an email        built fresh, or drawn from the generated pool
#   2. predict              the twin guesses, from its counters alone
#   3. answer               the person decides
#   4. update               the counters move, and the answer is logged
#
# Step 2 has to come before step 3. The prediction is only worth anything if
# it was committed before the outcome existed.

import random
from datetime import datetime

from backend.situation import make_random_situation


class NothingLeft(Exception):
    """There are no eligible generated emails to reuse."""


def next_email_id(emails, generated):
    """The next id in the single integer sequence shared by every email.

    The curated set holds the low numbers, so a freshly built email takes
    the first integer above both them and anything already generated.
    """
    used = [e["id"] for e in list(emails) + list(generated)
            if isinstance(e["id"], int)]
    return max(used, default=0) + 1


class DeliveryEngine:
    """Runs deliveries against a twin. Holds no UI state."""

    def __init__(self, twin, people, emails, answerer_for, generator,
                 builder=None, feedback=None, next_id=None, on_generated=None,
                 use_situations=True):
        self.twin = twin
        self.people = people
        self.emails = emails
        # Given a person id, return the email reader answering for them.
        self.answerer_for = answerer_for
        self.generator = generator
        self.builder = builder
        self.feedback = feedback
        self.next_id = next_id
        self.on_generated = on_generated
        self.use_situations = use_situations
        self._fingerprint_pool = None
        self._fingerprint_count = 0
        self._used_text = set()

    # ------------------------------------------------------------ choosing

    def pick(self, person, build_new=True, allow_repeats=True, generated=None):
        """The email for this delivery, and whether it was newly built."""
        from backend.email_generator import MAX_TRIES, fingerprint

        generated = generated if generated is not None else []
        if build_new:
            from backend.practice import valid_email
            if self.builder is None:
                raise ValueError("build_new needs a builder")
            identity = self.next_id() if self.next_id else next_email_id(self.emails, generated)
            if self._fingerprint_pool is not generated or len(generated) < self._fingerprint_count:
                self._used_text = {fingerprint(email) for email in self.emails}
                self._fingerprint_pool, self._fingerprint_count = generated, 0
            self._used_text.update(fingerprint(email) for email in generated[self._fingerprint_count:])
            self._fingerprint_count = len(generated)
            for _ in range(MAX_TRIES):
                email = self.builder.build_any(new_id=identity)
                if email is not None and not valid_email(email):
                    raise ValueError("The generated email is incomplete or has an invalid classification")
                if email is not None and fingerprint(email) not in self._used_text:
                    return email, True
            raise ValueError("Could not build a unique dynamic email; no answer was recorded")

        # Reuse complete generated messages, never the source templates.
        options = self._generated_options(person, generated, allow_repeats)
        if not options:
            raise NothingLeft("No unseen generated emails are available for %s" % person.id)
        return random.choice(options), False

    def _generated_options(self, person, generated, allow_repeats=False):
        from backend.email_generator import fingerprint
        seen = set() if allow_repeats else {r["email_id"] for r in self.twin.get_history(person.id)}
        used = {fingerprint(email) for email in self.emails}
        used.update(fingerprint(email) for email in generated if email["id"] in seen)
        options = []
        for email in generated:
            text = fingerprint(email)
            if email["id"] not in seen and text not in used:
                options.append(email)
                used.add(text)
        return options

    def available(self, targets=None, generated=None):
        """Those who still have an unseen generated email, for a no-repeats run."""
        return [person for person in (targets or self.people)
                if self._generated_options(person, generated or [])]

    # ------------------------------------------------------------ one round

    def deliver(self, person=None, build_new=True, allow_repeats=True,
                generated=None, targets=None):
        """Run one delivery and return what happened.

        Returns None when there is nothing left to ask, rather than raising -
        a caller looping over deliveries wants to stop, not handle an error.
        """
        if person is None:
            pool = (targets or self.people) if (build_new or allow_repeats) \
                else self.available(targets, generated)
            if not pool:
                return None
            person = random.choice(pool)

        try:
            email, was_built = self.pick(person, build_new, allow_repeats,
                                         generated)
        except NothingLeft:
            return None

        if was_built and generated is not None:
            generated.append(email)
            if self.on_generated:
                self.on_generated()

        situation = make_random_situation() if self.use_situations else None

        predicted = self.twin.predict(person.id, email)
        action = self.answerer_for(person.id).respond(email, situation)
        self.twin.update(person.id, email, action, source="sim")

        key = "false_report" if email["label"] == "legitimate" else email["cue"]
        history = self.twin.get_history(person.id, key)
        note = self.feedback.give_feedback(email, action, history) \
            if self.feedback else None

        # What this one answer did to that person's counter for this cue.
        last = history[-1]

        return {
            "time": datetime.now().strftime("%H:%M:%S"),
            "person": person.name,
            "person_id": person.id,
            "awareness": person.security_awareness,
            "email": email,
            "email_id": email["id"],
            "subject": email["subject"],
            "label": email["label"],
            "cue": email["cue"],
            "action": action,
            "built": was_built,
            "predicted": predicted,
            "p_before": last["p_before"],
            "p_after": last["p_click"],
            "yes": last["yes"],
            "no": last["no"],
            "all": last["all"],
            "feedback": note,
        }

    # ---------------------------------------------------------- many rounds

    def deliver_many(self, count, targets=None, build_new=True,
                     allow_repeats=True, generated=None, on_progress=None,
                     on_record=None):
        """Run many deliveries. Returns (delivered, skipped).

        on_progress(n, count) is called occasionally so a caller can draw a
        progress bar; on_record(record) gets every delivery as it happens.
        """
        delivered = skipped = 0
        for n in range(count):
            rec = self.deliver(build_new=build_new,
                               allow_repeats=allow_repeats,
                               generated=generated, targets=targets)
            if rec is None:
                skipped += 1
                continue
            delivered += 1
            if on_record:
                on_record(rec)
            if on_progress and (n % 200 == 0 or n == count - 1):
                on_progress(n + 1, count)
        return delivered, skipped

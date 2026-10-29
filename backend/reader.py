# reader.py
# A stand-in for a person that actually LOOKS AT THE EMAIL.
#
# The old SimulatedHuman decided by rolling a die against a secret number
# (hidden_probs). That number was invented, and the email played no part -
# which is what the course feedback objected to.
#
# This reader never uses a probability. It runs a list of checks against the
# real contents of the email, and says "spam" if any check it performs fires.
# Every check is a property you can point at:
#
#     sender domain does not match the hospital's
#     Reply-To goes somewhere other than the From address
#     the link text does not match where the link goes
#     an executable or macro attachment
#     credentials requested through a link
#     a deadline or countdown
#     a greeting with no name
#     secrecy, threats, or "do not reply"
#
# People differ by WHICH checks they run, not by how lucky they are. That is
# an observable habit, not a hidden number:
#
#     careless - glances at the display name only
#     average  - also checks the sender domain and notices deadlines
#     careful  - also checks Reply-To, hovers links, spots attachments
#
# Because nothing is random, the same person given the same email always
# answers the same way - which is what you would expect from a real reader.

REAL_DOMAIN = "ashbrookgeneral.example"

# Which checks each habit level performs, in the order a person would.
CHECKS_BY_SKILL = {
    "careless": [
        "generic_greeting",
    ],
    "average": [
        "generic_greeting",
        "sender_domain",
        "urgency_language",
        "dangerous_attachment",
    ],
    "careful": [
        "generic_greeting",
        "sender_domain",
        "urgency_language",
        "dangerous_attachment",
        "reply_to_mismatch",
        "link_mismatch",
        "credential_request",
        "pressure_language",
    ],
}

# security_awareness on a Persona maps straight onto a habit level.
SKILL_FOR_AWARENESS = {"low": "careless", "medium": "average", "high": "careful"}

URGENCY_WORDS = [
    "urgent", "immediately", "within 24 hours", "within 30 minutes",
    "before midnight", "expires today", "final notice", "action required",
    "in 1 hour", "today", "by friday", "48 hours", "72 hours", "3 working days",
]

PRESSURE_WORDS = [
    "do not reply", "keep this between us", "confidential", "do not forward",
    "this is your only notice", "escalated", "suspended", "collections",
    "will be deleted", "treated as accepted", "removed from the next",
]

CREDENTIAL_WORDS = [
    "sign in", "log in", "verify your", "confirm your", "re-verify",
    "reset your", "renew your password", "confirm details", "your account",
    "bank details", "social security", "date of birth",
]

ATTACHMENT_MARKERS = [".exe", ".zip", ".docm", ".xlsm", "enable content",
                      "attached:", "macro"]


def domain_of(address):
    """The domain part of an email address, or of a URL."""
    if not address:
        return ""
    if "://" in address:
        return address.split("://", 1)[1].split("/", 1)[0].lower()
    if "@" in address:
        return address.rsplit("@", 1)[1].lower()
    return address.lower()


class RuleReader:
    """Judges an email by inspecting it. No probabilities anywhere."""

    def __init__(self, persona=None, skill=None):
        self.persona = persona
        if skill:
            self.skill = skill
        else:
            awareness = getattr(persona, "security_awareness", "medium")
            self.skill = SKILL_FOR_AWARENESS.get(awareness, "average")
        self.checks = CHECKS_BY_SKILL[self.skill]

    # ------------------------------------------------------------- the checks
    # Each returns a reason string when it fires, or None when it does not.

    def check_sender_domain(self, email):
        domain = domain_of(email.get("sender_email", ""))
        if domain and domain != REAL_DOMAIN:
            return "sender domain is %s, not %s" % (domain, REAL_DOMAIN)
        return None

    def check_reply_to_mismatch(self, email):
        reply_to = email.get("reply_to")
        if not reply_to:
            return None
        if domain_of(reply_to) != domain_of(email.get("sender_email", "")):
            return "Reply-To goes to %s" % domain_of(reply_to)
        return None

    def check_link_mismatch(self, email):
        target = email.get("link_target")
        if not target:
            return None
        if domain_of(target) != domain_of(email.get("sender_email", "")):
            return "the link goes to %s" % domain_of(target)
        return None

    def check_urgency_language(self, email):
        text = (email.get("subject", "") + " " + email.get("body", "")).lower()
        for word in URGENCY_WORDS:
            if word in text:
                return "pushes a deadline: %r" % word
        return None

    def check_pressure_language(self, email):
        text = (email.get("subject", "") + " " + email.get("body", "")).lower()
        for word in PRESSURE_WORDS:
            if word in text:
                return "pressure or secrecy: %r" % word
        return None

    def check_credential_request(self, email):
        body = email.get("body", "").lower()
        has_link = bool(email.get("link_target")) or "http" in body
        if not has_link:
            return None
        for word in CREDENTIAL_WORDS:
            if word in body:
                return "asks you to %r behind a link" % word
        return None

    def check_dangerous_attachment(self, email):
        body = email.get("body", "").lower()
        for marker in ATTACHMENT_MARKERS:
            if marker in body:
                return "attachment marker: %r" % marker
        return None

    def check_generic_greeting(self, email):
        body = email.get("body", "")
        opening = body.strip().split("\n", 1)[0].lower()
        for greeting in ("greetings:", "dear nursing staff", "dear staff",
                         "hello all", "doctor,"):
            if opening.startswith(greeting):
                return "greeting with no name: %r" % opening[:28]
        return None

    # ------------------------------------------------------------- the verdict

    def inspect(self, email):
        """Run this reader's checks. Returns the reasons that fired."""
        reasons = []
        for name in self.checks:
            reason = getattr(self, "check_" + name)(email)
            if reason:
                reasons.append(reason)
        return reasons

    def judge(self, email):
        """'spam' if anything this reader checks looks wrong, else 'not spam'."""
        return "spam" if self.inspect(email) else "not spam"

    # The quick checks - the ones you still do when you are glancing. The
    # rest (Reply-To, hovering a link, reading for pressure) take deliberate
    # effort and are the first to go when someone is rushing.
    QUICK_CHECKS = 2

    def checks_for(self, situation):
        """Which checks this reader actually performs right now.

        Rushing does not change what someone knows, it changes how much they
        bother to look. No probability here: given the same moment, the same
        checks run every time.
        """
        if not situation:
            return self.checks
        rushed = (situation.get("busy_now") == "very busy"
                  or situation.get("time_of_day") == "night")
        if rushed:
            return self.checks[:self.QUICK_CHECKS]
        return self.checks

    def respond(self, email, situation=None):
        """Same shape as SimulatedHuman.respond, so it is a drop-in."""
        active = self.checks_for(situation)
        fired = [getattr(self, "check_" + name)(email) for name in active]
        verdict = "spam" if any(fired) else "not spam"
        if verdict == "spam":
            return "report"
        # They trusted it. On a phishing email that is the click; on a
        # genuine one it is the correct non-action.
        return "click" if email["label"] == "phishing" else "ignore"

    def explain(self, email):
        """Why this reader answered the way it did."""
        reasons = self.inspect(email)
        if reasons:
            return "Flagged as spam because: " + "; ".join(reasons)
        missed = []
        for name, method in (("sender_domain", self.check_sender_domain),
                             ("reply_to_mismatch", self.check_reply_to_mismatch),
                             ("link_mismatch", self.check_link_mismatch)):
            if name not in self.checks and method(email):
                missed.append(method(email))
        if missed:
            return ("Trusted it. A more careful reader would have seen: "
                    + "; ".join(missed))
        return "Trusted it, and nothing this reader checks looked wrong."

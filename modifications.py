# modifications.py
# Every way an email is made phishy, as a catalogue of named modifications.
#
# A phishing email is a legitimate-looking one with things done to it. This
# module holds each of those things separately, so a new email can be built
# by choosing which to apply - and because each modification knows the tell
# it introduces, the red flags come out automatically rather than being
# written by hand.
#
# Four families:
#
#   ADDRESS   what the sender address does      (8 ways a domain can lie)
#   LINK      what the link and Reply-To do
#   LANGUAGE  how the words pressure the reader
#   STRUCTURE what the message is missing or carries
#
# Every modification is:
#   name         a short id, used in data
#   family       which of the four above
#   explains     the teaching note - what this trick is, in general
#   apply(email) returns (changed email, the red flag it introduced)
#
# Nothing here invents a probability. A modification either was applied or
# was not, and the red flag names exactly which.

import random
import re

REAL_DOMAIN = "ashbrookgeneral.example"

# Characters that look alike. Used for typosquatting.
LOOKALIKE_SWAPS = [("l", "i"), ("l", "1"), ("o", "0"), ("rn", "m"), ("m", "rn")]

URGENCY_LINES = [
    "This must be completed before midnight.",
    "You have 24 hours to respond.",
    "Action is required within 30 minutes.",
    "Unless this is done today, access will be suspended.",
    "Final notice - respond within 3 working days.",
]

PRESSURE_LINES = [
    "Please keep this between us until it is announced.",
    "This is your only notice.",
    "Non-completion is escalated to your manager.",
    "This is an automatically generated email, please do not reply.",
    "Do not forward this message.",
]

CREDENTIAL_LINES = [
    "Sign in with your network account to continue.",
    "Confirm your bank details so payment can be released.",
    "Verify your account to avoid interruption.",
    "Re-enter your password to keep access.",
]

GENERIC_GREETINGS = ["Greetings:", "Dear Staff,", "Hello all,", "Dear User,"]

ATTACHMENT_LINES = [
    "Attached: Patient_Records_Update.exe (2.1 MB)",
    "Attached: Remittance_October.zip (contains Remittance_October.pdf.exe)",
    "Attached: Salary_Info_2026.xlsm",
    "Attached: Statement_Q4.docm - choose Enable Content to view it.",
]


class Modification:
    """One way of making an email phishy."""

    name = "modification"
    family = "other"
    explains = ""

    def apply(self, email):
        """Return (changed copy, red flag). Never mutates the original."""
        raise NotImplementedError

    def __repr__(self):
        return "<%s %s>" % (self.family, self.name)


# =========================================================== ADDRESS family

class LookalikeDomain(Modification):
    name = "lookalike"
    family = "address"
    explains = ("Extra words bolted onto the real name, so it reads right at "
                "a glance but is owned by someone else.")

    def apply(self, email):
        e = dict(email)
        base = REAL_DOMAIN.split(".")[0]
        word = random.choice(["support", "it", "hr", "secure", "alerts", "billing"])
        domain = "%s-%s.example" % (base, word)
        local = e.get("sender_email", "noreply@x").split("@")[0]
        e["sender_email"] = "%s@%s" % (local, domain)
        return e, "lookalike domain: %s, not %s" % (domain, REAL_DOMAIN)


class Typosquat(Modification):
    name = "typosquat"
    family = "address"
    explains = ("A character swapped for one that looks identical - an 'i' for "
                "an 'l', or a zero for an 'o'.")

    def apply(self, email):
        e = dict(email)
        base = REAL_DOMAIN.split(".")[0]
        for old, new in random.sample(LOOKALIKE_SWAPS, len(LOOKALIKE_SWAPS)):
            if old in base:
                domain = base.replace(old, new, 1) + ".example"
                break
        else:
            domain = base + ".example"
        local = e.get("sender_email", "noreply@x").split("@")[0]
        e["sender_email"] = "%s@%s" % (local, domain)
        return e, ("typosquatted domain: %s - one character swapped for a "
                   "lookalike" % domain)


class SubdomainMisdirection(Modification):
    name = "subdomain_misdirection"
    family = "address"
    explains = ("The real name sits at the FRONT as a subdomain; the owner is "
                "the LAST domain. Read a domain right to left.")

    def apply(self, email):
        e = dict(email)
        owner = random.choice(["verify-center", "secure-portal", "alerts-hub"]) + ".example"
        local = e.get("sender_email", "noreply@x").split("@")[0]
        e["sender_email"] = "%s@%s.%s" % (local, REAL_DOMAIN, owner)
        return e, ("subdomain misdirection: %s is only a label in front - the "
                   "real owner is %s" % (REAL_DOMAIN, owner))


class ExtraEnding(Modification):
    name = "extra_ending"
    family = "address"
    explains = ("The genuine name with a further ending bolted on, so the "
                "registered domain is not the one you recognise.")

    def apply(self, email):
        e = dict(email)
        local = e.get("sender_email", "noreply@x").split("@")[0]
        # Only reserved endings, so nothing can ever resolve.
        domain = REAL_DOMAIN + random.choice([".net", ".org", ".com"])
        e["sender_email"] = "%s@%s" % (local, domain)
        return e, "an extra ending bolted on: %s" % domain


class ForgedFrom(Modification):
    name = "forged_from"
    family = "address"
    explains = ("The From line shows the real domain. A From line can be "
                "forged, so it proves nothing on its own.")

    def apply(self, email):
        e = dict(email)
        local = e.get("sender_email", "noreply@x").split("@")[0]
        e["sender_email"] = "%s@%s" % (local, REAL_DOMAIN)
        return e, ("the From line shows the real domain - a From line can be "
                   "forged, so it proves nothing")


class FreeProvider(Modification):
    name = "free_provider"
    family = "address"
    explains = ("A corporate role sent from a consumer mail provider. Payroll "
                "and managers never write from a personal service.")

    def apply(self, email):
        e = dict(email)
        local = e.get("sender_email", "noreply@x").split("@")[0]
        domain = random.choice(["mailbox-provider.example", "outlook-mail.example",
                                "webmail-free.example"])
        e["sender_email"] = "%s@%s" % (local, domain)
        return e, "a consumer mail provider, not the hospital: %s" % domain


class DisplayNameFraud(Modification):
    name = "display_name_fraud"
    family = "address"
    explains = ("The display name is a department you trust; the address "
                "behind it is a machine-generated mailbox somewhere else.")

    def apply(self, email):
        e = dict(email)
        mailbox = "user%d" % random.randint(1000, 9999)
        domain = random.choice(["mail-relay-svc.example", "smtp-out.example"])
        e["sender_email"] = "%s@%s" % (mailbox, domain)
        return e, ("the display name says %r; the address is %s@%s"
                   % (e.get("sender_name", "?"), mailbox, domain))


class UnrelatedDomain(Modification):
    name = "unrelated"
    family = "address"
    explains = ("Makes no attempt to look like the hospital - it imitates a "
                "supplier, insurer or authority instead.")

    def apply(self, email):
        e = dict(email)
        domain = random.choice(["claims-processing.example", "invoice-centre.example",
                                "accreditation-review.example"])
        local = e.get("sender_email", "noreply@x").split("@")[0]
        e["sender_email"] = "%s@%s" % (local, domain)
        return e, "an outside domain pretending to be an authority: %s" % domain


# ============================================================== LINK family

class ReplyToMismatch(Modification):
    name = "reply_to_mismatch"
    family = "link"
    explains = "A reply goes somewhere other than the address shown in From."

    def apply(self, email):
        e = dict(email)
        local = e.get("sender_email", "noreply@x").split("@")[0]
        domain = random.choice(["mail-redirect.example", "reply-handler.example",
                                "ashbrookgeneral-hr.example"])
        e["reply_to"] = "%s@%s" % (local, domain)
        return e, "Reply-To goes somewhere else entirely: %s" % domain


class HiddenLink(Modification):
    name = "hidden_link"
    family = "link"
    explains = ("The clickable text says one thing and the link goes "
                "somewhere else. Hovering is the only way to see it.")

    def apply(self, email):
        e = dict(email)
        text = random.choice(["Click here", "Verify your account",
                              "Review the document", "Confirm details"])
        target = "https://%s/%s" % (
            random.choice(["secure-login.example", "account-verify.example",
                           "ashbrook-support.example"]),
            random.choice(["verify", "login", "reset", "confirm"]))
        e["link_text"] = text
        e["link_target"] = target
        e["body"] = (e.get("body", "").rstrip() + "\n\n" + text)
        return e, ("hover before clicking: the link reads %r but goes to %s"
                   % (text, target.split("//")[1].split("/")[0]))


class CredentialRequest(Modification):
    name = "credential_request"
    family = "link"
    explains = "Asks for a password, bank details or identity behind a link."

    def apply(self, email):
        e = dict(email)
        line = random.choice(CREDENTIAL_LINES)
        e["body"] = e.get("body", "").rstrip() + "\n\n" + line
        return e, "asks you to act on credentials: %r" % line


# ========================================================== LANGUAGE family

class UrgencyLanguage(Modification):
    name = "urgency"
    family = "language"
    explains = "A deadline or countdown, so you act before you check."

    def apply(self, email):
        e = dict(email)
        line = random.choice(URGENCY_LINES)
        e["body"] = e.get("body", "").rstrip() + "\n\n" + line
        return e, "pushes a deadline: %r" % line


class PressureLanguage(Modification):
    name = "pressure"
    family = "language"
    explains = ("Secrecy, threats or 'do not reply' - all of which remove the "
                "easiest way to check.")

    def apply(self, email):
        e = dict(email)
        line = random.choice(PRESSURE_LINES)
        e["body"] = e.get("body", "").rstrip() + "\n\n" + line
        return e, "pressure or secrecy: %r" % line


class Misspelling(Modification):
    name = "misspelling"
    family = "language"
    explains = ("Spelling and grammar slips. Real internal mail is proofread; "
                "bulk phishing often is not.")

    # Deliberate, recognisable slips rather than random noise.
    SLIPS = [
        ("please", "pls"), ("received", "recieved"), ("your", "you're"),
        ("account", "accont"), ("immediately", "immediatly"),
        ("verification", "verificaton"), ("required", "requried"),
    ]

    def apply(self, email):
        e = dict(email)
        body = e.get("body", "")
        used = None
        for right, wrong in random.sample(self.SLIPS, len(self.SLIPS)):
            pattern = re.compile(re.escape(right), re.IGNORECASE)
            if pattern.search(body):
                body = pattern.sub(wrong, body, count=1)
                used = (right, wrong)
                break
        if used is None:
            # Nothing to misspell - add a line that carries one.
            used = random.choice(self.SLIPS)
            body = body.rstrip() + "\n\nPls complete this %s." % used[1]
        e["body"] = body
        return e, "misspelling: %r written as %r" % used


# ========================================================= STRUCTURE family

class GenericGreeting(Modification):
    name = "generic_greeting"
    family = "structure"
    explains = ("A greeting with no name, because it went to everyone at "
                "once. Real internal mail knows who you are.")

    def apply(self, email):
        e = dict(email)
        greeting = random.choice(GENERIC_GREETINGS)
        body = e.get("body", "")
        # Replace an existing opening line if there is one.
        lines = body.split("\n")
        if lines and lines[0].strip().endswith((",", ":")):
            lines[0] = greeting
            body = "\n".join(lines)
        else:
            body = greeting + "\n\n" + body
        e["body"] = body
        return e, "greeting with no name: %r" % greeting


class DangerousAttachment(Modification):
    name = "dangerous_attachment"
    family = "structure"
    explains = ("An executable or macro file dressed as a document. Opening "
                "it is what runs the payload.")

    def apply(self, email):
        e = dict(email)
        line = random.choice(ATTACHMENT_LINES)
        e["body"] = e.get("body", "").rstrip() + "\n\n" + line
        return e, "dangerous attachment: %s" % line.replace("Attached: ", "")


class NoContactDetails(Modification):
    name = "no_contact"
    family = "structure"
    explains = ("No name, extension or department to call. Genuine internal "
                "mail tells you who sent it and how to reach them.")

    def apply(self, email):
        e = dict(email)
        # Strip any "extension NNNN" sign-off.
        e["body"] = re.sub(r",?\s*extension\s*\d+", "", e.get("body", ""))
        return e, "no name, no extension, no department to check with"


# ============================================================== the catalogue

ALL = [
    LookalikeDomain(), Typosquat(), SubdomainMisdirection(), ExtraEnding(),
    ForgedFrom(), FreeProvider(), DisplayNameFraud(), UnrelatedDomain(),
    ReplyToMismatch(), HiddenLink(), CredentialRequest(),
    UrgencyLanguage(), PressureLanguage(), Misspelling(),
    GenericGreeting(), DangerousAttachment(), NoContactDetails(),
]

BY_NAME = {m.name: m for m in ALL}
BY_FAMILY = {}
for _m in ALL:
    BY_FAMILY.setdefault(_m.family, []).append(_m)


def get(name):
    return BY_NAME[name]


def family(name):
    return list(BY_FAMILY.get(name, []))


def apply_all(email, names):
    """Apply several modifications in order.

    Returns (changed email, list of red flags). Address modifications are
    applied first so later ones see the final sender.
    """
    order = {"address": 0, "link": 1, "language": 2, "structure": 3}
    chosen = sorted((BY_NAME[n] for n in names),
                    key=lambda m: order.get(m.family, 9))

    result, flags = dict(email), []
    for mod in chosen:
        result, flag = mod.apply(result)
        flags.append(flag)
    return result, flags


if __name__ == "__main__":
    print("%d modifications in %d families\n" % (len(ALL), len(BY_FAMILY)))
    for fam, mods in BY_FAMILY.items():
        print("%s (%d)" % (fam.upper(), len(mods)))
        for m in mods:
            print("   %-24s %s" % (m.name, m.explains[:58]))
        print()

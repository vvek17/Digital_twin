"""Assigned manual practice. Answers and scores stay in the existing history."""

import csv
import json
import random

from backend.email_builder import EmailBuilder
from backend.email_generator import MAX_TRIES, fingerprint
from backend.engine import next_email_id


PRACTICE_FILE = "practice_sessions.json"
MAX_PRACTICE_EMAILS = 1000000  # Same delivery ceiling as the existing Run workflow.


def valid_email(email):
    return (isinstance(email, dict)
            and all(key in email for key in ("id", "label", "cue", "subject", "body", "sender_email"))
            and isinstance(email["id"], (str, int)) and not isinstance(email["id"], bool)
            and email["label"] in ("phishing", "legitimate")
            and all(isinstance(email[key], str) for key in ("subject", "body", "sender_email")))


def load_sessions(data):
    path = data / PRACTICE_FILE
    if not path.exists():
        return []
    if path.is_symlink():
        raise ValueError("Practice sessions must be a regular data file")
    try:
        payload = json.loads(path.read_text())
        if payload.get("version") != 1 or not isinstance(payload.get("sessions"), list):
            raise ValueError("Expected version 1 and a sessions list")
        sessions = payload["sessions"]
        identities, requests = set(), set()
        for session in sessions:
            if (not isinstance(session, dict) or not isinstance(session.get("id"), str)
                    or not isinstance(session.get("request_id"), str)
                    or not isinstance(session.get("person_id"), (str, int))
                    or isinstance(session["person_id"], bool)
                    or type(session.get("count")) is not int
                    or not 1 <= session["count"] <= MAX_PRACTICE_EMAILS
                    or not isinstance(session.get("emails"), list)
                    or len(session["emails"]) != session["count"]):
                raise ValueError("Invalid practice session")
            if session["id"] in identities or session["request_id"] in requests:
                raise ValueError("Duplicate session or request ID")
            identities.add(session["id"])
            requests.add(session["request_id"])
            email_ids = set()
            for email in session["emails"]:
                if not valid_email(email) or email["id"] in email_ids:
                    raise ValueError("Invalid or repeated email in a practice session")
                email_ids.add(email["id"])
        return sessions
    except (ValueError, KeyError, TypeError, AttributeError) as exc:
        raise ValueError("Could not read practice sessions: %s" % exc) from exc


def merge_session_emails(generated, sessions, originals=(), stored=()):
    """Make assigned email snapshots available to the existing reports and builder."""
    known = {e["id"]: e for e in list(originals) + list(generated)}
    merged = list(generated)
    records = list(stored) + [email for session in sessions for email in session["emails"]]
    for email in records:
        existing = known.get(email["id"])
        if existing is not None:
            if any(existing.get(key) != email.get(key) for key in ("subject", "body", "label", "cue")):
                raise ValueError("Email ID %s has conflicting practice content" % email["id"])
        else:
            merged.append(email)
            known[email["id"]] = email
    return merged


def current_session(workspace, person_id):
    return next((session for session in reversed(getattr(workspace, "practice_sessions", []))
                 if session["person_id"] == person_id), None)


def practice_emails(workspace, person_id):
    session = current_session(workspace, person_id)
    return session["emails"] if session is not None else workspace.generated


def session_records(workspace, session):
    email_ids = {email["id"] for email in session["emails"]}
    return [record for record in workspace.twin.get_history(session["person_id"])
            if record.get("source") == "app" and "correct" in record and record["email_id"] in email_ids]


def next_dynamic_id(emails, generated, data):
    """Keep IDs above existing mail, CSV exports and retained historical answers."""
    identity = next_email_id(emails, generated)
    csv_path = data / "generated_emails.csv"
    if csv_path.exists():
        with csv_path.open(newline="") as stream:
            for row in csv.DictReader(stream):
                try:
                    identity = max(identity, int(row["ID"]) + 1)
                except (ValueError, KeyError, TypeError):
                    continue
    history_path = data / "history_log.jsonl"
    if history_path.exists():
        with history_path.open() as stream:
            for line in stream:
                try:
                    record = json.loads(line)
                    identity = max(identity, int(record["email_id"]) + 1)
                except (ValueError, KeyError, TypeError):
                    continue
    return identity


def prepare_emails(workspace, person_id, count, on_progress=None):
    """Reuse generated mail first; only build the shortfall with the existing builder."""
    seen_ids = {record["email_id"] for record in workspace.twin.get_history(person_id)
                if record.get("source") == "app"}
    candidates = [email for email in workspace.generated if email["id"] not in seen_ids]
    random.shuffle(candidates)
    selected, used_ids = [], set()
    # New IDs must not disguise an unchanged template or a previous question.
    used_text = {fingerprint(email) for email in workspace.emails}
    used_text.update(fingerprint(email) for email in workspace.generated if email["id"] in seen_ids)

    def keep(email):
        if email is None:
            return False
        if not valid_email(email):
            raise ValueError("A generated email is incomplete or has an invalid classification; nothing was assigned")
        if email["id"] in seen_ids or email["id"] in used_ids or fingerprint(email) in used_text:
            return False
        selected.append(email)
        used_ids.add(email["id"])
        used_text.add(fingerprint(email))
        if on_progress and (len(selected) % 50 == 0 or len(selected) == count):
            on_progress(len(selected), count)
        return True

    for email in candidates:
        keep(email)
        if len(selected) == count:
            return selected
    identity = next_dynamic_id(workspace.emails, workspace.generated, workspace.data)
    builder = EmailBuilder(workspace.generator)
    for _ in range((count - len(selected)) * MAX_TRIES):
        email = builder.build_any(new_id=identity)
        identity += 1
        keep(email)
        if len(selected) == count:
            return selected
    raise ValueError("Requested %d emails, but only %d unique dynamic emails could be prepared. "
                     "No practice session was assigned. Try again or prepare more emails first."
                     % (count, len(selected)))

"""Shared data loading and human training; research operations live in admin."""

from datetime import datetime
from pathlib import Path

from backend import store
from backend.feedback import FeedbackModule
from backend.generator import EmailGenerator
from backend.persona import load_people
from backend.twin import TwinPredictor
from database.build import build
from backend.practice import load_sessions, merge_session_emails, practice_emails


class Workspace:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.data = self.root / "data"
        self.people = load_people(str(self.data / "hospital_people.json"))
        self.people_by_id = {p.id: p for p in self.people}
        db_path = self.data / "simulation.db"
        if not db_path.exists():
            build(str(db_path), data_dir=self.data)
        self.generator = EmailGenerator(db_path=str(db_path))
        self.emails = self.generator.emails
        self.twin = TwinPredictor(log_path=str(self.data / "history_log.jsonl"),
                                  csv_path=str(self.data / "history.csv"),
                                  results_path=str(self.data / "results.csv"))
        self.twin.rebuild_from_log()
        self.twin.people_by_id = self.people_by_id
        try:
            self.generated = store.load_generated(str(self.data / "generated_emails.json"))
            self.practice_sessions = load_sessions(self.data)
            self.generated = merge_session_emails(self.generated, self.practice_sessions, self.emails)
        except Exception:
            self.generator.db.close()
            raise
        self.feedback = FeedbackModule("detailed")

    def save(self, generated=False):
        self.twin.save(str(self.data / "people_history.json"), self.people_by_id,
                       export_dir=str(self.data))
        if generated:
            store.save_generated(self.generated, str(self.data / "generated_emails.json"))

    def close(self):
        self.generator.db.close()


def training_records(workspace, person_id):
    return [r for r in workspace.twin.get_history(person_id)
            if r.get("source") == "app" and "correct" in r]


def unanswered_emails(workspace, person_id):
    # Simulated answers must not exhaust a human trainee's practice queue.
    seen = {r["email_id"] for r in training_records(workspace, person_id)}
    from backend.email_generator import fingerprint
    pool = practice_emails(workspace, person_id)
    used_text = {fingerprint(email) for email in workspace.emails}
    used_text.update(fingerprint(email) for email in pool if email["id"] in seen)
    unanswered = []
    for email in pool:
        if email["id"] not in seen and fingerprint(email) not in used_text:
            unanswered.append(email)
            used_text.add(fingerprint(email))
    return unanswered


def submit_answer(workspace, person_id, email_id, said_spam):
    if person_id not in workspace.people_by_id:
        raise ValueError("Unknown training persona")
    if not isinstance(said_spam, bool):
        raise ValueError("Choose Spam or Not spam")
    # Reload the saved observations before writing; do not reuse a stale twin
    # after an administrator restores data or another session submits an answer.
    workspace.twin.rebuild_from_log()
    workspace.practice_sessions = load_sessions(workspace.data)
    workspace.generated[:] = merge_session_emails(
        workspace.generated, workspace.practice_sessions, workspace.emails,
        store.load_generated(str(workspace.data / "generated_emails.json")))
    email = next((e for e in unanswered_emails(workspace, person_id) if e["id"] == email_id), None)
    if email is None:
        raise ValueError("This email is unknown or has already been answered")
    action = "report" if said_spam else ("click" if email["label"] == "phishing" else "ignore")
    workspace.twin.update(person_id, email, action, source="app")
    workspace.save()
    record = workspace.twin.get_history(person_id)[-1]
    person = workspace.people_by_id[person_id]
    store.save_response({"time": datetime.now().isoformat(timespec="seconds"),
                         "person_id": person_id, "person_name": person.name,
                         "email_id": email_id, "cue": email["cue"], "label": email["label"],
                         "said": record["said"], "truth": record["truth"],
                         "correct": record["correct"], "action": action},
                        str(workspace.data / "responses.json"))
    key = "false_report" if email["label"] == "legitimate" else email["cue"]
    history = [r for r in training_records(workspace, person_id) if r["key"] == key]
    return workspace.feedback.give_feedback(email, action, history)

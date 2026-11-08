"""Email content, saved verdicts, review state and duplicate-click regressions."""

from copy import deepcopy
from html import escape
from html.parser import HTMLParser
import json

import pytest
from streamlit.testing.v1 import AppTest

from backend.feedback import FeedbackModule
from frontend.email_presentation import email_markup, feedback_markup
from tests.test_app_roles import ROOT, project, seed_training
from backend.training import Workspace


@pytest.fixture
def workspace(project):
    value = Workspace(project)
    seed_training(value)
    yield value
    value.close()


class MessageText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.inside = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if dict(attrs).get("class") == "alert-mail-body":
            self.inside = True

    def handle_endtag(self, tag):
        if tag == "div" and self.inside:
            self.inside = False

    def handle_data(self, data):
        if self.inside:
            self.parts.append(data)


def markup(app):
    return "\n".join(node.proto.body for node in app.get("html"))


def open_email(workspace, email):
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    app.session_state["training_order"] = [email["id"]] + [
        e["id"] for e in workspace.generated if e["id"] != email["id"]]
    return app.run()


def events(workspace):
    path = workspace.data / "history_log.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def test_reader_preserves_long_message_links_paragraphs_and_signature():
    body = ("First paragraph & details.\n\n"
            "https://one.example/path?a=1&b=2\nhttps://two.example/check\n\n"
            "A long paragraph " * 80) + "\n\nBest wishes,\nA. Sender\nExtension 1234"
    email = {"subject": "Long subject <with literal markup> " * 12,
             "sender_name": 'Sender <img src="https://remote.example/image">',
             "sender_email": "sender@familiar.example", "reply_to": "reply@other.example",
             "body": body, "link_text": "Check details", "link_target": "https://other.example/review"}
    before = deepcopy(email)
    rendered = email_markup(email)
    parsed = MessageText()
    parsed.feed(rendered)
    assert "".join(parsed.parts) == body
    assert escape(email["subject"]) in rendered
    assert email["sender_email"] in rendered and email["reply_to"] in rendered
    assert email["link_target"] in rendered
    assert "<img" not in rendered and "<script" not in rendered
    assert "<a " not in rendered  # Inspect destinations without leaving the exercise.
    assert email == before


@pytest.mark.parametrize("count", [0, 1, 9])
def test_feedback_keeps_all_source_evidence_and_details(count):
    email = {"label": "phishing", "cue": "authority", "technique": "Fixture technique",
             "red_flags": ["Evidence %d <literal text>" % i for i in range(count)],
             "key_defense": "The original learning note.", "reply_to": "reply@example.test",
             "link_text": "Visible words", "link_target": "https://destination.example/a?b=1&c=2"}
    feedback = FeedbackModule().give_feedback(email, "report")
    feedback["history_note"] = "Original history and streak information."
    before = deepcopy(feedback)
    rendered = feedback_markup(feedback, {"correct": True, "said": "spam"}, email)
    assert rendered.count("<li>") == count
    for value in [feedback["headline"], *feedback["tells"], feedback["defense"],
                  feedback["history_note"], feedback["technique"], feedback["reply_to"],
                  email["link_text"], email["link_target"]]:
        assert escape(value) in rendered
    assert "No additional evidence" in rendered if not count else "<li>" in rendered
    assert feedback == before


def test_genuine_takeaway_uses_existing_note_without_domain_based_classification():
    email = {"label": "legitimate", "cue": "none", "safe_signs": ["Verify through the staff portal."],
             "key_defense": "Original genuine-email learning note.", "sender_email": "sender@example.test"}
    feedback = FeedbackModule().give_feedback(email, "ignore")
    rendered = feedback_markup(feedback, {"correct": True, "said": "not spam"}, email)
    assert "Genuine email (not spam)" in rendered
    assert email["key_defense"] in rendered
    # The identical address with an authoritative phishing verdict stays phishing.
    phishing = dict(email, label="phishing", red_flags=["Source evidence."])
    result = FeedbackModule().give_feedback(phishing, "report")
    assert "Phishing email" in feedback_markup(result, {"correct": True, "said": "spam"}, phishing)


@pytest.mark.parametrize("label,choice,correct", [
    ("phishing", "Spam", True), ("phishing", "Not spam", False),
    ("legitimate", "Spam", False), ("legitimate", "Not spam", True),
])
def test_all_decisions_keep_answered_email_and_existing_scores(workspace, label, choice, correct):
    email = next(e for e in workspace.generated if e["label"] == label)
    app = open_email(workspace, email)
    next(b for b in app.button if b.label == choice).click().run()
    assert not app.exception and not app.error
    saved = events(workspace)
    assert len(saved) == 1 and saved[0]["email_id"] == email["id"]
    assert saved[0]["correct"] is correct and saved[0]["source"] == "app"
    rendered = markup(app)
    assert ("Correct answer" if correct else "Incorrect answer") in rendered
    assert escape(email["subject"]) in rendered
    assert escape(email["body"]) in rendered
    assert email["key_defense"] in rendered
    metrics = {m.label: m.value for m in app.metric}
    assert metrics == {"Answered": "1", "Correct": str(int(correct)),
                       "Accuracy": "100%" if correct else "0%"}
    assert [b.label for b in app.button] == ["Next email"]
    next(b for b in app.button if b.label == "Next email").click().run()
    assert not app.exception and not app.error
    assert len(events(workspace)) == 1
    assert not app.session_state["training_review"].get(saved[0]["person_id"])
    assert {b.label for b in app.button} == {"Spam", "Not spam"}


def test_duplicate_and_stale_intents_never_submit_another_message(workspace):
    email = workspace.generated[0]
    app = open_email(workspace, email)
    person_id = app.selectbox(key="training_person_id").value
    next(b for b in app.button if b.label == "Spam").click().run()
    intent = {"person_id": person_id, "email_id": email["id"], "said_spam": True}
    app.session_state["training_pending"] = intent
    app.run()
    assert len(events(workspace)) == 1 and not app.exception
    next(b for b in app.button if b.label == "Next email").click().run()
    app.session_state["training_pending"] = intent
    app.run()
    assert len(events(workspace)) == 1 and not app.exception
    next(b for b in app.button if b.label == "Not spam").click().run()
    saved = events(workspace)
    assert len(saved) == 2 and len({r["email_id"] for r in saved}) == 2


def test_save_failure_restores_choices_without_adding_a_record(workspace, monkeypatch):
    import frontend.training_views as views
    original = views.submit_answer
    app = open_email(workspace, workspace.generated[0])

    def fail(*args, **kwargs):
        raise OSError("Fixture save failure")

    monkeypatch.setattr(views, "submit_answer", fail)
    next(b for b in app.button if b.label == "Spam").click().run()
    assert not app.exception and events(workspace) == []
    assert any("Fixture save failure" in item.value for item in app.error)
    assert all(not b.disabled for b in app.button)
    monkeypatch.setattr(views, "submit_answer", original)
    next(b for b in app.button if b.label == "Spam").click().run()
    assert not app.exception and not app.error and len(events(workspace)) == 1


def test_inbox_progress_counts_only_human_answers(workspace):
    email = workspace.generated[0]
    workspace.twin.update(workspace.people[0].id, email, "click", source="sim")
    app = open_email(workspace, email)
    next(b for b in app.button if b.label == "Spam").click().run()
    assert len(events(workspace)) == 2
    assert {m.label: m.value for m in app.metric} == {
        "Answered": "1", "Correct": "1", "Accuracy": "100%"}


def test_review_stays_with_its_persona_when_switching_staff(workspace):
    app = open_email(workspace, workspace.generated[0])
    first, second = workspace.people[:2]
    next(b for b in app.button if b.label == "Spam").click().run()
    app.selectbox(key="training_person_id").set_value(second.id).run()
    assert not app.exception and not app.error
    assert "Correct answer" not in markup(app)
    assert {b.label for b in app.button} == {"Spam", "Not spam"}
    app.selectbox(key="training_person_id").set_value(first.id).run()
    assert "Correct answer" in markup(app)
    assert [b.label for b in app.button] == ["Next email"]
    assert len(events(workspace)) == 1


def test_final_email_keeps_feedback_and_complete_progress(workspace):
    final = next(e for e in workspace.generated if e["label"] == "legitimate")
    person_id = workspace.people[0].id
    for email in workspace.generated:
        if email["id"] != final["id"]:
            workspace.twin.update(person_id, email,
                                  "report" if email["label"] == "phishing" else "ignore", source="app")
    app = open_email(workspace, final)
    next(b for b in app.button if b.label == "Not spam").click().run()
    assert not app.exception and not app.error and not app.button
    assert "Correct answer" in markup(app) and escape(final["body"]) in markup(app)
    assert any("All practice emails completed" in item.value for item in app.success)
    assert {m.label: m.value for m in app.metric} == {
        "Answered": str(len(workspace.generated)), "Correct": str(len(workspace.generated)), "Accuracy": "100%"}

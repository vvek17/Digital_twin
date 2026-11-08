"""Authorized assignment and manual completion, using temporary data only."""

import json

import pytest
from streamlit.testing.v1 import AppTest

from backend.admin import AdminService
from backend import store
from backend.practice import PRACTICE_FILE, current_session, load_sessions, session_records
from backend.training import Workspace, submit_answer, unanswered_emails
from tests.test_app_roles import ROOT, admin_app, authorized_service, project, workspace


def seed_generated(workspace, count):
    pool = []
    for index in range(count):
        original = workspace.emails[index % len(workspace.emails)]
        pool.append(dict(original, id=1000 + index, built_from=original["id"],
                         subject="Existing dynamic email %d" % index,
                         body=original["body"] + "\n\nFixture reference %d" % index))
    store.save_generated(pool, str(workspace.data / "generated_emails.json"))
    return pool


def history(workspace):
    path = workspace.data / "history_log.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


@pytest.mark.parametrize("count", [1, 5, 10, 501])
def test_exact_counts_reuse_existing_dynamic_mail_without_answering(workspace, monkeypatch, count):
    pool = seed_generated(workspace, count)
    before = {p.name: p.read_bytes() for p in workspace.data.iterdir() if p.is_file()}

    def unexpected_build(*args, **kwargs):
        raise AssertionError("Existing emails must be reused before generating more")

    monkeypatch.setattr("backend.practice.EmailBuilder.build_any", unexpected_build)
    service = authorized_service(workspace.root)
    result = service.assign_practice(workspace, workspace.people[0].id, count, "request-%d" % count)
    assert result["count"] == count and len(result["emails"]) == count
    assert {e["id"] for e in result["emails"]} == {e["id"] for e in pool}
    assert history(workspace) == [] and not (workspace.data / "responses.json").exists()
    assert len(load_sessions(workspace.data)) == 1
    assert all((workspace.data / name).read_bytes() == content for name, content in before.items())


@pytest.mark.parametrize("count", [0, -1, 2.5, "5", True, None, 1000001])
def test_invalid_counts_are_rejected_before_assignment(workspace, count):
    service = authorized_service(workspace.root)
    with pytest.raises(ValueError, match="whole number"):
        service.assign_practice(workspace, workspace.people[0].id, count, "invalid-count")
    assert not (workspace.data / PRACTICE_FILE).exists() and history(workspace) == []


def test_active_jobs_block_assignments(workspace):
    service = authorized_service(workspace.root)
    service.job_provider = lambda: True
    with pytest.raises(RuntimeError, match="Live or Run"):
        service.assign_practice(workspace, workspace.people[0].id, 5, "active-job-request")
    assert not (workspace.data / PRACTICE_FILE).exists()


def test_authorization_is_rechecked_after_preparing_emails(workspace, monkeypatch):
    from backend.practice import prepare_emails
    seed_generated(workspace, 5)
    service = authorized_service(workspace.root)

    def revoke(*args, **kwargs):
        emails = prepare_emails(*args, **kwargs)
        service.authority.logout(service.token_provider())
        return emails

    monkeypatch.setattr("backend.practice.prepare_emails", revoke)
    with pytest.raises(PermissionError):
        service.assign_practice(workspace, workspace.people[0].id, 5, "revoked-request")
    assert not (workspace.data / PRACTICE_FILE).exists()


def test_authorization_participant_and_duplicate_requests_are_enforced(workspace):
    seed_generated(workspace, 10)
    person = workspace.people[0]
    with pytest.raises(PermissionError):
        AdminService(workspace.root).assign_practice(workspace, person.id, 5, "not-authorized")
    service = authorized_service(workspace.root)
    with pytest.raises(ValueError, match="Unknown practice participant"):
        service.assign_practice(workspace, "MISSING", 5, "unknown-person")
    first = service.assign_practice(workspace, person.id, 5, "same-request")
    original = (workspace.data / PRACTICE_FILE).read_bytes()
    assert service.assign_practice(workspace, person.id, 5, "same-request") == first
    assert (workspace.data / PRACTICE_FILE).read_bytes() == original
    with pytest.raises(ValueError, match="different assignment"):
        service.assign_practice(workspace, workspace.people[1].id, 5, "same-request")
    with pytest.raises(ValueError, match="unfinished practice"):
        service.assign_practice(workspace, person.id, 10, "second-request")
    assert len(load_sessions(workspace.data)) == 1


def test_only_shortfall_is_built_and_existing_csv_ids_are_reserved(workspace, monkeypatch):
    pool = seed_generated(workspace, 2)
    (workspace.data / "generated_emails.csv").write_text("ID,Subject,Body\n9000,Existing,Existing\n")
    built_ids = []

    def build(self, new_id=None, **kwargs):
        built_ids.append(new_id)
        return dict(workspace.emails[0], id=new_id, subject="New %s" % new_id,
                    body="New dynamic body %s" % new_id, built_from=workspace.emails[0]["id"])

    monkeypatch.setattr("backend.practice.EmailBuilder.build_any", build)
    result = authorized_service(workspace.root).assign_practice(
        workspace, workspace.people[0].id, 5, "shortfall-request")
    assert built_ids == [9001, 9002, 9003]
    assert {e["id"] for e in pool} <= {e["id"] for e in result["emails"]}
    assert history(workspace) == []


def test_insufficient_unique_emails_never_save_a_shorter_session(workspace, monkeypatch):
    def repeated(self, new_id=None, **kwargs):
        return dict(workspace.emails[0], id=new_id)

    monkeypatch.setattr("backend.practice.EmailBuilder.build_any", repeated)
    with pytest.raises(ValueError, match="only 0 unique dynamic emails"):
        authorized_service(workspace.root).assign_practice(
            workspace, workspace.people[0].id, 5, "insufficient-request")
    assert not (workspace.data / PRACTICE_FILE).exists()
    assert not (workspace.data / "generated_emails.json").exists()
    assert history(workspace) == [] and not (workspace.data / "responses.json").exists()


def test_failed_atomic_assignment_does_not_change_prior_data(workspace, monkeypatch):
    import backend.admin as admin
    seed_generated(workspace, 5)
    before = {p.name: p.read_bytes() for p in workspace.data.iterdir() if p.is_file()}
    original = admin._atomic_bytes

    def fail(path, data):
        if path.name == PRACTICE_FILE:
            raise OSError("Fixture disk failure")
        return original(path, data)

    monkeypatch.setattr(admin, "_atomic_bytes", fail)
    with pytest.raises(OSError, match="Fixture disk failure"):
        authorized_service(workspace.root).assign_practice(
            workspace, workspace.people[0].id, 5, "write-failure-request")
    assert not (workspace.data / PRACTICE_FILE).exists()
    assert all((workspace.data / name).read_bytes() == content for name, content in before.items())


def test_people_have_separate_queues_and_sessions_survive_restart(workspace):
    seed_generated(workspace, 20)
    service = authorized_service(workspace.root)
    first, second, unassigned = workspace.people[:3]
    one = service.assign_practice(workspace, first.id, 5, "first-person-request")
    two = service.assign_practice(workspace, second.id, 10, "second-person-request")
    for email in one["emails"][:2]:
        result = submit_answer(workspace, first.id, email["id"], email["label"] == "phishing")
        assert result["was"] == email["label"]
    fresh = Workspace(workspace.root)
    try:
        assert len(unanswered_emails(fresh, first.id)) == 3
        assert len(unanswered_emails(fresh, second.id)) == 10
        assert len(unanswered_emails(fresh, unassigned.id)) == len(fresh.generated)
        assert fresh.twin.get_score(unassigned.id)["answered"] == 0
        assert current_session(fresh, first.id)["id"] == one["id"]
        assert current_session(fresh, second.id)["id"] == two["id"]
        assert all(r["person_id"] == first.id and r["source"] == "app" for r in history(workspace))
        assert fresh.twin.get_score(first.id)["correct"] == 2
        assert fresh.twin.get_score(second.id)["answered"] == 0
        known = {email["id"] for email in fresh.generated}
        assert {email["id"] for email in one["emails"] + two["emails"]} <= known
    finally:
        fresh.close()


def test_complete_then_assign_again_preserves_history_and_avoids_repeats(workspace):
    seed_generated(workspace, 15)
    service = authorized_service(workspace.root)
    person_id = workspace.people[0].id
    first = service.assign_practice(workspace, person_id, 5, "completed-first-request")
    for email in first["emails"]:
        submit_answer(workspace, person_id, email["id"], email["label"] == "phishing")
    old_history = (workspace.data / "history_log.jsonl").read_bytes()
    old_scores = (workspace.data / "scores.csv").read_bytes()
    second = service.assign_practice(workspace, person_id, 10, "next-session-request")
    assert not {e["id"] for e in first["emails"]} & {e["id"] for e in second["emails"]}
    assert (workspace.data / "history_log.jsonl").read_bytes() == old_history
    assert (workspace.data / "scores.csv").read_bytes() == old_scores
    for email in second["emails"]:
        submit_answer(workspace, person_id, email["id"], email["label"] == "phishing")
    assert len(history(workspace)) == 15
    assert len(session_records(workspace, second)) == 10
    assert workspace.twin.get_score(person_id)["correct"] == 15


def test_sessions_participate_in_integrity_backups_restore_and_reset(workspace):
    seed_generated(workspace, 5)
    service = authorized_service(workspace.root)
    session = service.assign_practice(workspace, workspace.people[0].id, 5, "maintenance-request")
    assert service.integrity()["issues"] == []
    status = next(row for row in service.file_status() if row["file"] == PRACTICE_FILE)
    assert status["records"] == 1
    backup = service.create_backup()
    (workspace.data / PRACTICE_FILE).write_text('{"version":1,"sessions":[]}')
    service.restore_backup(backup["name"], "RESTORE")
    assert load_sessions(workspace.data)[0] == session
    reset = service.reset_all_results("RESET ALL RESULTS")
    assert load_sessions(workspace.data) == []
    service.restore_backup(reset["backup"], "RESTORE")
    assert load_sessions(workspace.data)[0] == session


def test_corrupt_assignment_data_fails_closed_without_overwriting_it(workspace):
    path = workspace.data / PRACTICE_FILE
    path.write_text('{"version":1,"sessions":"damaged"}')
    with pytest.raises(ValueError, match="Could not read practice sessions"):
        authorized_service(workspace.root).assign_practice(
            workspace, workspace.people[0].id, 5, "corrupt-source-request")
    assert path.read_text() == '{"version":1,"sessions":"damaged"}'


def test_email_studio_preserves_complete_emails_for_practice_and_unique_ids(workspace, monkeypatch):
    seed_generated(workspace, 2)
    service = authorized_service(workspace.root)
    first = service.assign_practice(workspace, workspace.people[0].id, 2, "studio-first-request")
    calls = []

    def generate(self, technique=None, save=True, **kwargs):
        calls.append(save)
        return dict(workspace.emails[0], id=52, subject="Studio fixture %d" % len(calls),
                    body="Studio fixture body %d" % len(calls), timestamp="fixture timestamp",
                    entities_used={}, modifications=[], built_from=workspace.emails[0]["id"])

    monkeypatch.setattr("backend.email_generator.EmailGeneratorLLM.generate", generate)
    made, rejected = service.generate_emails(workspace, 2)
    assert calls == [False, False] and rejected == 0
    assert min(email["id"] for email in made) > max(email["id"] for email in first["emails"])
    # Both stores retain the exact message; the JSON also retains feedback/header fields.
    pool = store.load_generated(str(workspace.data / "generated_emails.json"))
    assert all(email in pool for email in made)
    assert service.integrity()["issues"] == []
    next_person = workspace.people[1].id
    second = service.assign_practice(workspace, next_person, 4, "studio-second-request")
    assert {email["id"] for email in made} <= {email["id"] for email in second["emails"]}
    assert history(workspace) == []


def test_invalid_generated_classification_cannot_be_saved_as_an_assignment(workspace, monkeypatch):
    def invalid(self, new_id=None, **kwargs):
        return dict(workspace.emails[0], id=new_id, label="invalid")

    monkeypatch.setattr("backend.practice.EmailBuilder.build_any", invalid)
    with pytest.raises(ValueError, match="invalid classification"):
        authorized_service(workspace.root).assign_practice(
            workspace, workspace.people[0].id, 5, "invalid-email-request")
    assert not (workspace.data / PRACTICE_FILE).exists()


def test_ids_do_not_reuse_retained_history_when_old_generated_content_is_missing(workspace):
    historical = dict(workspace.emails[0], id=9000, subject="Historical dynamic example")
    workspace.twin.update(workspace.people[1].id, historical, "report", source="sim")
    original = (workspace.data / "history_log.jsonl").read_bytes()
    result = authorized_service(workspace.root).assign_practice(
        workspace, workspace.people[0].id, 5, "historical-id-request")
    assert min(email["id"] for email in result["emails"]) > 9000
    assert (workspace.data / "history_log.jsonl").read_bytes() == original


def test_existing_live_workspace_keeps_new_assignments_and_avoids_id_collisions(workspace):
    service = authorized_service(workspace.root)
    first_delivery = service.deliver_one(workspace, build_new=True)
    session = service.assign_practice(workspace, workspace.people[1].id, 5, "live-sync-request")
    second_delivery = service.deliver_one(workspace, build_new=True)
    assigned_ids = {email["id"] for email in session["emails"]}
    assert second_delivery["email_id"] > max(assigned_ids)
    # Reusing that complete generated message in another person's practice is valid.
    assert first_delivery["email"] in session["emails"]
    service.save_workspace(workspace, generated=True)
    stored = store.load_generated(str(workspace.data / "generated_emails.json"))
    assert assigned_ids | {first_delivery["email_id"], second_delivery["email_id"]} <= {
        email["id"] for email in stored}
    assert len(history(workspace)) == 2  # Only the two explicitly simulated deliveries answered.
    assert service.integrity()["issues"] == []


def test_new_participant_appears_in_existing_selector_and_can_be_assigned(workspace):
    seed_generated(workspace, 5)
    path = workspace.data / "hospital_people.json"
    payload = json.loads(path.read_text())
    payload["people"].append(dict(payload["people"][0], job_id="P99", name="New Training Member"))
    path.write_text(json.dumps(payload))
    app = admin_app("Person")
    picker = app.selectbox(key="admin_person_id")
    assert any("P99" in option for option in picker.options)
    picker.set_value("P99").run()
    next(button for button in app.button if button.label == "Assign practice").click().run()
    assert not app.exception and not app.error
    assert load_sessions(workspace.data)[0]["person_id"] == "P99"


@pytest.mark.parametrize("count", [1, 5, 10])
def test_admin_assigns_and_inbox_completes_the_exact_manual_session(workspace, count):
    seed_generated(workspace, 10)
    admin = admin_app("Person")
    person_id = admin.selectbox(key="admin_person_id").value
    field = next(field for field in admin.number_input if field.label == "Practice emails")
    field.set_value(count)
    next(button for button in admin.button if button.label == "Assign practice").click().run()
    assert not admin.exception and not admin.error
    assert not any(button.label == "Assign practice" for button in admin.button)
    assert history(workspace) == []
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert any("Assigned practice" in item.value for item in app.caption)
    for index in range(count):
        next(button for button in app.button if button.label == "Spam").click().run()
        assert not app.exception and not app.error
        assert next(m.value for m in app.metric if m.label == "Answered") == str(index + 1)
        if index < count - 1:
            next(button for button in app.button if button.label == "Next email").click().run()
    assert not app.button and len(history(workspace)) == count
    assert all(record["person_id"] == person_id and record["source"] == "app" for record in history(workspace))
    app.radio(key="training_view").set_value("Training progress").run()
    assert not app.exception and not app.error
    assert next(m.value for m in app.metric if m.label == "Answered") == str(count)
    assert any("alert-mail-body" in node.proto.body for node in app.get("html"))
    admin.run()
    assert any(button.label == "Assign practice" for button in admin.button)


def test_assignment_error_is_visible_and_keeps_the_form_usable(workspace, monkeypatch):
    def fail(*args, **kwargs):
        raise ValueError("Requested 5 emails; no complete practice session could be prepared")

    monkeypatch.setattr("backend.practice.prepare_emails", fail)
    app = admin_app("Person")
    next(button for button in app.button if button.label == "Assign practice").click().run()
    assert not app.exception
    assert any("no complete practice session" in error.value for error in app.error)
    assert any(button.label == "Assign practice" for button in app.button)
    assert not (workspace.data / PRACTICE_FILE).exists() and history(workspace) == []


def test_empty_inbox_never_uses_templates_or_generates_during_render(project):
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not app.exception and not app.button
    assert any("No generated practice emails" in item.value for item in app.info)
    before = {p.name: p.read_bytes() for p in (project / "data").iterdir()}
    app.run()
    assert {p.name: p.read_bytes() for p in (project / "data").iterdir()} == before
    assert not (project / "data/generated_emails.json").exists()


def test_unassigned_inbox_refreshes_new_generated_mail_and_rejects_static_answers(workspace):
    person = workspace.people[0]
    with pytest.raises(ValueError, match="unknown"):
        submit_answer(workspace, person.id, workspace.emails[0]["id"], True)
    pool = seed_generated(workspace, 2)
    # Submission itself refreshes storage, even when this workspace predates generation.
    feedback = submit_answer(workspace, person.id, pool[0]["id"], True)
    assert feedback["tells"] == pool[0]["red_flags"]
    with pytest.raises(ValueError, match="already been answered"):
        submit_answer(workspace, person.id, pool[0]["id"], True)
    fresh = Workspace(workspace.root)
    try:
        assert [e["id"] for e in unanswered_emails(fresh, person.id)] == [pool[1]["id"]]
    finally:
        fresh.close()
    assert len(history(workspace)) == 1


def test_reuse_simulation_uses_only_generated_mail_and_respects_no_repeats(workspace):
    pool = seed_generated(workspace, 2)
    service = authorized_service(workspace.root)
    person = workspace.people[0]
    # Many old static answers must not make a fresh dynamic pool look exhausted.
    for email in workspace.emails:
        workspace.twin.update(person.id, email, "report", source="sim")
    original = (workspace.data / "history_log.jsonl").read_bytes()
    delivered = []
    result = service.run_many(workspace, 3, targets=[person], build_new=False,
                              allow_repeats=False, on_record=delivered.append)
    assert result == (2, 1)
    assert {r["email_id"] for r in delivered} == {e["id"] for e in pool}
    assert all(not r["built"] and r["email"] in pool for r in delivered)
    assert (workspace.data / "history_log.jsonl").read_bytes().startswith(original)
    assert service.deliver_one(workspace, person=person, build_new=False, allow_repeats=True)
    assert store.load_generated(str(workspace.data / "generated_emails.json")) == pool


def test_empty_reuse_simulation_does_not_fall_back_to_static_mail(workspace):
    assert authorized_service(workspace.root).run_many(workspace, 2, build_new=False) == (0, 2)
    assert history(workspace) == []


def test_duplicate_text_is_not_repeated_even_under_a_new_generated_id(workspace):
    pool = seed_generated(workspace, 1)
    duplicate = dict(pool[0], id=2000)
    store.save_generated(pool + [duplicate], str(workspace.data / "generated_emails.json"))
    submit_answer(workspace, workspace.people[0].id, pool[0]["id"], True)
    assert unanswered_emails(workspace, workspace.people[0].id) == []
    assert authorized_service(workspace.root).deliver_one(
        workspace, person=workspace.people[0], build_new=False, allow_repeats=False) is None


@pytest.mark.parametrize("payload", ['{broken', '{"emails":null}',
                                       '{"emails":[{"id":100,"label":"unknown"}]}'])
def test_damaged_generated_pool_is_not_overwritten_or_replaced_with_static_mail(workspace, payload):
    path = workspace.data / "generated_emails.json"
    path.write_text(payload)
    with pytest.raises(ValueError):
        authorized_service(workspace.root).run_many(workspace, 2)
    assert path.read_text() == payload and history(workspace) == []


def test_real_generation_storage_answers_feedback_and_database_projection(workspace):
    from backend.email_generator import EmailGeneratorLLM
    from database.build import build
    from database.db import Database
    service = authorized_service(workspace.root)
    originals = (workspace.data / "hospital_emails_mixed.json").read_bytes()
    # Exercise Email Studio's real generator, not a mocked replacement.
    made, rejected = service.generate_emails(workspace, 2, "Malware")
    assert len(made) + rejected == 2 and made
    maker = EmailGeneratorLLM(static=workspace.emails,
                             csv_path=str(workspace.data / "generated_emails.csv"))
    genuine = maker.generate_legitimate()
    genuine["id"] = max(e["id"] for e in made) + 1
    base = workspace.generator.by_id[genuine["built_from"]]
    assert genuine["safe_signs"] == base["safe_signs"] and genuine["safe_signs"]
    store.save_generated(made + [genuine], str(workspace.data / "generated_emails.json"))
    session = service.assign_practice(workspace, workspace.people[0].id, len(made) + 1, "real-flow-request")
    assert {e["label"] for e in session["emails"]} == {"phishing", "legitimate"}
    restored = Workspace(workspace.root)
    try:
        for email in session["emails"]:
            result = submit_answer(restored, workspace.people[0].id, email["id"], email["label"] == "phishing")
            assert result["was"] == email["label"]
            assert result["tells"] == email.get("red_flags" if email["label"] == "phishing" else "safe_signs", [])
            if email.get("link_target"):
                assert result["hidden_link"] == (email["link_text"], email["link_target"])
        assert restored.twin.get_score(workspace.people[0].id)["accuracy"] == 1
        assert all(record["source"] == "app" for record in history(restored))
        known = {e["id"]: e for e in restored.generated}
        assert all(known[e["id"]] == e for e in session["emails"])
    finally:
        restored.close()
    projection = workspace.data / "verification.db"
    build(str(projection), data_dir=workspace.data)
    db = Database(str(projection), build_if_missing=False)
    try:
        assert db.person_scores()[0]["accuracy"] == 1
        assert {r["email_id"] for r in db.deliveries()} == {e["id"] for e in session["emails"]}
    finally:
        db.close()
    assert (workspace.data / "hospital_emails_mixed.json").read_bytes() == originals


def test_command_line_runners_deliver_dynamic_mail_and_keep_no_save_read_only(project):
    import subprocess
    import sys
    for script, args in (("main.py", ["P01", "3", "--reader"]),
                         ("live.py", ["--rounds", "3", "--speed", "0", "--plain"])):
        completed = subprocess.run([sys.executable, str(ROOT / script), *args], cwd=project,
                                   capture_output=True, text=True, timeout=30)
        assert completed.returncode == 0, completed.stderr
    records = [json.loads(line) for line in (project / "data/history_log.jsonl").read_text().splitlines()]
    generated = store.load_generated(str(project / "data/generated_emails.json"))
    assert len(records) == 6 and len(generated) == 6
    catalogue = {e["id"]: e for e in generated}
    assert all(r["email_id"] > 51 and r["subject"] == catalogue[r["email_id"]]["subject"]
               and r["label"] == catalogue[r["email_id"]]["label"] for r in records)
    before = {p.name: p.read_bytes() for p in (project / "data").iterdir()}
    for script, args in (("main.py", ["P01", "2", "--reader", "--no-save"]),
                         ("live.py", ["--rounds", "2", "--speed", "0", "--plain", "--no-save"])):
        completed = subprocess.run([sys.executable, str(ROOT / script), *args], cwd=project,
                                   capture_output=True, text=True, timeout=30)
        assert completed.returncode == 0, completed.stderr
    assert {p.name: p.read_bytes() for p in (project / "data").iterdir()} == before


def test_partial_simulation_keeps_messages_for_already_recorded_answers(workspace):
    def stop_after_one(record):
        raise RuntimeError("Fixture interrupted batch")

    with pytest.raises(RuntimeError, match="interrupted batch"):
        authorized_service(workspace.root).run_many(workspace, 5, on_record=stop_after_one)
    recorded = history(workspace)
    assert len(recorded) == 1
    generated = store.load_generated(str(workspace.data / "generated_emails.json"))
    assert generated[0]["id"] == recorded[0]["email_id"]
    assert generated[0]["subject"] == recorded[0]["subject"]


def test_simulation_rejects_an_invalid_generated_label_before_recording(workspace, monkeypatch):
    def invalid(self, new_id=None, **kwargs):
        return dict(workspace.emails[0], id=new_id, label="unknown")

    monkeypatch.setattr("backend.email_builder.EmailBuilder.build_any", invalid)
    with pytest.raises(ValueError, match="invalid classification"):
        authorized_service(workspace.root).run_many(workspace, 1)
    assert history(workspace) == []


def test_model_analysis_includes_session_snapshots_without_changing_features_or_targets(workspace):
    from backend.ml_model import build_dataset, featurize, twin_baseline
    service = authorized_service(workspace.root)
    person = workspace.people[0]
    session = service.assign_practice(workspace, person.id, 2, "model-dynamic-request")
    for index, email in enumerate(session["emails"]):
        correct_choice = email["label"] == "phishing"
        submit_answer(workspace, person.id, email["id"], correct_choice if index else not correct_choice)
    assert not (workspace.data / "generated_emails.json").exists()  # Snapshots are sufficient.
    frame = build_dataset(str(workspace.data / "history_log.jsonl"), people=workspace.people)
    assert len(frame) == 2 and set(frame["fell_for_it"]) == {0, 1}
    for email in session["emails"]:
        row = frame.set_index("email_id").loc[email["id"]]
        for key, value in featurize(person, email).items():
            assert row[key] == value
    assert 0 <= twin_baseline(frame, str(workspace.data / "history_log.jsonl")) <= 1
    # Only email lookup changes: the existing comparison algorithm remains intact.
    result = service.compare_models(workspace, 10)
    assert len(result) == 10 * len(workspace.people)

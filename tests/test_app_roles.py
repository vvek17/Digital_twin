"""Role separation and end-to-end connections using copied research sources."""

import hashlib
import json
from pathlib import Path
import shutil

import pytest
from streamlit.testing.v1 import AppTest

from backend.admin import AdminService
from backend.auth import AdminAuthority
from backend.training import Workspace, submit_answer, training_records, unanswered_emails
from frontend import runtime


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def project(tmp_path, monkeypatch):
    data = tmp_path / "data"
    data.mkdir()
    for name in ("hospital_people.json", "hospital_emails_mixed.json"):
        shutil.copyfile(ROOT / "data" / name, data / name)
    monkeypatch.setattr(runtime, "PROJECT_ROOT", tmp_path)
    return tmp_path


@pytest.fixture
def workspace(project):
    value = Workspace(project)
    yield value
    value.close()


def authorized_service(root):
    authority = AdminAuthority(lambda: "test-secret", "backend-tests")
    token = authority.login("test-secret")
    return AdminService(root, authority, lambda: token)


def seed_training(workspace):
    """Complete generated fixtures; never expose source templates as questions."""
    from backend import store
    from backend.email_builder import EmailBuilder
    builder = EmailBuilder(workspace.generator)
    pool = [builder.build_one(new_id=1000), builder.build_one(new_id=1001),
            builder.build_legitimate(base=workspace.generator.by_id[38], new_id=1002),
            builder.build_legitimate(base=workspace.generator.by_id[39], new_id=1003)]
    workspace.generated[:] = pool
    store.save_generated(pool, str(workspace.data / "generated_emails.json"))
    return pool


def admin_app(section="Dashboard"):
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run().switch_page("pages/admin.py")
    app.secrets["admin_password"] = "test-secret"
    app.session_state["admin_session_id"] = "ui-tests"
    app.session_state["admin_auth_token"] = AdminAuthority(
        lambda: "test-secret", "ui-tests").login("test-secret")
    app.session_state["admin_section"] = section
    return app.run()


def test_services_deny_unauthorized_reads_writes_and_research(project):
    service = AdminService(project)
    before = {p: p.read_bytes() for p in (project / "data").iterdir()}
    actions = [lambda: service.file_status(), lambda: service.database_status(),
               lambda: service.integrity(), lambda: service.list_backups(),
               lambda: service.create_backup(), lambda: service.load_workspace(),
               lambda: service.restore_backup("alert-test.zip", "RESTORE"),
               lambda: service.clear_caches(lambda: None, lambda: None),
               lambda: service.generate_emails(None, 1), lambda: service.run_many(None, 1),
               lambda: service.deliver_one(None), lambda: service.save_workspace(None),
               lambda: service.compare_models(None, 10), lambda: service.generated_csv()]
    for action in actions:
        with pytest.raises(PermissionError):
            action()
    assert {p: p.read_bytes() for p in (project / "data").iterdir()} == before
    assert not (project / "backups").exists()
    assert not (project / ".admin.lock").exists()


def test_grants_are_session_bound_expire_revoke_and_recheck_secret(monkeypatch):
    import backend.auth as auth
    secret = ["original"]
    authority = AdminAuthority(lambda: secret[0], "one")
    token = authority.login("original")
    authority.require(token)
    with pytest.raises(PermissionError):
        AdminAuthority(lambda: secret[0], "two").require(token)
    with pytest.raises(PermissionError):
        authority.require(hashlib.sha256(b"original").hexdigest())
    secret[0] = "changed"
    with pytest.raises(PermissionError):
        authority.require(token)
    token = authority.login("changed")
    authority.logout(token)
    with pytest.raises(PermissionError):
        authority.require(token)
    token = authority.login("changed")
    current = auth.time.time()
    monkeypatch.setattr(auth.time, "time", lambda: current + 9 * 3600)
    with pytest.raises(PermissionError):
        authority.require(token)


def test_backend_job_guard_cannot_be_bypassed_by_false_argument(project):
    service = authorized_service(project)
    service.job_provider = lambda: True
    with pytest.raises(RuntimeError, match="Live or Run"):
        service.create_backup(active_job=False)


def test_full_reset_is_confirmed_backed_up_and_rebuilds_empty_results(workspace):
    seed_training(workspace)
    service = authorized_service(workspace.root)
    person = workspace.people[0]
    submit_answer(workspace, person.id, workspace.generated[0]["id"], True)
    service.run_many(workspace, 2)
    source_bytes = {name: (workspace.data / name).read_bytes() for name in (
        "hospital_people.json", "hospital_emails_mixed.json")}
    old_log = (workspace.data / "history_log.jsonl").read_bytes()
    with pytest.raises(ValueError, match="RESET ALL RESULTS"):
        service.reset_all_results("RESET")
    assert (workspace.data / "history_log.jsonl").read_bytes() == old_log
    result = service.reset_all_results("RESET ALL RESULTS")
    assert result["records_cleared"] == 3
    assert service._read_backup(result["backup"])["history_log.jsonl"] == old_log
    for name, content in source_bytes.items():
        assert (workspace.data / name).read_bytes() == content
    fresh = Workspace(workspace.root)
    try:
        assert sum(len(v) for v in fresh.twin.history.values()) == 0
        assert fresh.generated == []
        assert unanswered_emails(fresh, person.id) == []
        assert fresh.generator.db.count("deliveries") == 0
        assert all(v["a"] == v["b"] == 0 for counters in fresh.twin.counters.values()
                   for v in counters.values())
        assert json.loads((fresh.data / "responses.json").read_text()) == []
        # A new human answer still gets correctly headed CSVs after reset.
        session = service.assign_practice(fresh, person.id, 1, "after-reset-request")
        submit_answer(fresh, person.id, session["emails"][0]["id"], False)
        assert len((fresh.data / "history.csv").read_text().splitlines()) == 2
    finally:
        fresh.close()
    audit = [json.loads(line) for line in (workspace.data / "admin_audit.jsonl").read_text().splitlines()]
    reset_audit = next(row for row in reversed(audit) if row["action"] == "reset_all_results")
    assert reset_audit["outcome"] == "success"
    assert json.loads(reset_audit["detail"])["backup"] == result["backup"]


def test_full_reset_rolls_back_if_replacement_fails(workspace, monkeypatch):
    seed_training(workspace)
    import backend.admin as admin
    service = authorized_service(workspace.root)
    submit_answer(workspace, workspace.people[0].id, workspace.generated[0]["id"], True)
    original_log = (workspace.data / "history_log.jsonl").read_bytes()
    original_responses = (workspace.data / "responses.json").read_bytes()
    original_write = admin._atomic_bytes
    failed = False

    def fail_once(path, data):
        nonlocal failed
        if path == workspace.data / "responses.json" and not failed:
            failed = True
            raise OSError("reset fixture failure")
        return original_write(path, data)

    monkeypatch.setattr(admin, "_atomic_bytes", fail_once)
    with pytest.raises(OSError, match="fixture failure"):
        service.reset_all_results("RESET ALL RESULTS")
    assert (workspace.data / "history_log.jsonl").read_bytes() == original_log
    assert (workspace.data / "responses.json").read_bytes() == original_responses
    assert service.list_backups()


def test_training_uses_existing_update_logic_and_hydrates_teaching_notes(workspace):
    seed_training(workspace)
    person = workspace.people[0]
    phishing = next(e for e in workspace.generated if e["label"] == "phishing")
    legitimate = next(e for e in workspace.generated if e["label"] == "legitimate")
    assert phishing["red_flags"]
    assert legitimate["safe_signs"]
    # A simulation may have used every curated email; human practice remains available.
    for email in workspace.emails:
        workspace.twin.update(person.id, email, "report", source="sim")
    assert len(unanswered_emails(workspace, person.id)) == len(workspace.generated)
    feedback = submit_answer(workspace, person.id, phishing["id"], True)
    assert feedback["tells"] == phishing["red_flags"]
    assert len(training_records(workspace, person.id)) == 1
    assert len(unanswered_emails(workspace, person.id)) == len(workspace.generated) - 1
    assert workspace.twin.get_history(person.id)[-1]["source"] == "app"
    responses = json.loads((workspace.data / "responses.json").read_text())
    assert responses[-1]["correct"] is True
    with pytest.raises(ValueError, match="already been answered"):
        submit_answer(workspace, person.id, phishing["id"], False)
    for name in ("people_history.json", "scores.csv", "click_rates.csv", "person_summary.csv"):
        assert (workspace.data / name).exists()


def test_main_app_only_renders_training_and_records_answer(project):
    temporary = Workspace(project)
    seed_training(temporary)
    temporary.close()
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not app.exception and not app.error
    assert not app.tabs
    assert app.radio(key="training_view").options == ["Inbox", "Training progress"]
    assert {b.label for b in app.button} == {"Spam", "Not spam"}
    assert not app.toggle and not app.number_input
    person_id = app.selectbox(key="training_person_id").value
    next(b for b in app.button if b.label == "Spam").click().run()
    assert not app.exception and not app.error
    records = [json.loads(line) for line in (project / "data/history_log.jsonl").read_text().splitlines()]
    assert len(records) == 1
    assert records[0]["person_id"] == person_id and records[0]["source"] == "app"
    app.radio(key="training_view").set_value("Training progress").run()
    assert any(m.label == "Answered" and m.value == "1" for m in app.metric)


def test_admin_sections_render_and_logout_protects_access(project):
    app = admin_app()
    for section in ["Dashboard", "Live", "Person", "All history", "Run", "Model", "Emails", "System"]:
        app.radio(key="admin_section").set_value(section).run()
        assert not app.exception, section
        assert not app.error, (section, [e.value for e in app.error])
    next(b for b in app.button if b.label == "Log out").click().run()
    assert not app.exception
    assert not app.dataframe and not app.radio
    assert any(b.label == "Log in" for b in app.button)


def test_two_main_screens_keep_their_tools_and_admin_login(project):
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert [link.proto.label for link in app.get("page_link")] == ["App", "Admin"]
    assert app.radio(key="training_view").label == "App tools"
    app.secrets["admin_password"] = "navigation-fixture"
    app.switch_page("pages/admin.py").run()
    assert [link.proto.label for link in app.get("page_link")] == ["App", "Admin"]
    assert not app.radio and any(button.label == "Log in" for button in app.button)
    app.text_input(key="admin_password_input").set_value("navigation-fixture")
    next(button for button in app.button if button.label == "Log in").click().run()
    assert not app.exception and not app.error
    assert app.radio(key="admin_section").label == "Admin tools"
    assert "Person" in app.radio(key="admin_section").options
    app.switch_page("app.py").run()
    assert not app.exception and not app.error
    assert app.radio(key="training_view").label == "App tools"
    assert not app.radio(key="training_view").disabled


def test_session_queries_work_after_streamlit_changes_script_threads(project):
    temporary = Workspace(project)
    seed_training(temporary)
    temporary.close()
    from concurrent.futures import ThreadPoolExecutor

    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    session_workspace = app.session_state["workspace"]
    person = session_workspace.people[0]

    def use_generator():
        email = session_workspace.generator.get_targeted(person)
        assert email and "red_flags" in email
        session_workspace.close()
        return email["id"]

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert all(executor.map(lambda _: use_generator(), range(4)))
    # Data changes trigger disposal and reload on a later script thread too.
    submit_answer(session_workspace, person.id, session_workspace.generated[0]["id"], True)
    app.run()
    assert not app.exception and not app.error
    next(b for b in app.button if b.label == "Spam").click().run()
    assert not app.exception and not app.error


def test_admin_run_and_generation_write_only_fixture_data(project):
    app = admin_app("Run")
    app.number_input[0].set_value(3)
    next(b for b in app.button if b.label == "Run now").click().run()
    assert not app.exception and not app.error
    assert app.session_state["run_running"] is False
    records = [json.loads(line) for line in (project / "data/history_log.jsonl").read_text().splitlines()]
    assert len(records) == 3 and all(r["source"] == "sim" for r in records)
    assert len(json.loads((project / "data/generated_emails.json").read_text())["emails"]) == 3
    assert (project / "data/email_scores.csv").exists()
    app.radio(key="admin_section").set_value("Emails").run()
    next(b for b in app.button if b.label == "Generate").click().run()
    assert not app.exception and not app.error
    assert (project / "data/generated_emails.csv").exists()
    audit = [json.loads(line) for line in (project / "data/admin_audit.jsonl").read_text().splitlines()]
    assert {r["action"] for r in audit} >= {"simulate_batch", "generate_emails"}


def test_research_auth_is_revalidated_after_login(workspace):
    service = authorized_service(workspace.root)
    service.authority.logout(service.token_provider())
    with pytest.raises(PermissionError):
        service.run_many(workspace, 1)
    assert not (workspace.data / "history_log.jsonl").exists()


def test_live_service_and_model_connection(workspace):
    service = authorized_service(workspace.root)
    rec = service.deliver_one(workspace, build_new=True)
    assert rec and rec["email_id"] > max(e["id"] for e in workspace.emails)
    service.save_workspace(workspace, generated=True)
    # Two-class training fixture, using the unchanged twin update implementation.
    person = workspace.people[0]
    for email in workspace.emails:
        action = "click" if email["label"] == "phishing" and email["id"] % 2 else "report"
        workspace.twin.update(person.id, email, action, source="sim")
    result = service.compare_models(workspace, 10)
    assert len(result) == 10 * len(workspace.people)
    assert {"ml_right", "twin_right", "actually_fell"} <= set(result.columns)


def test_model_button_runs_through_authorized_backend(workspace):
    person = workspace.people[0]
    for email in workspace.emails:
        workspace.twin.update(person.id, email, "click" if email["id"] % 2 else "report", source="sim")
    app = admin_app("Model")
    assert any("The model test has two scoring problems" in w.value for w in app.warning)
    app.number_input[0].set_value(10)
    next(b for b in app.button if b.label == "Build and test").click().run()
    assert not app.exception and not app.error
    assert any(m.label == "Machine learning model" for m in app.metric)
    assert len(app.session_state["model_results"]) == 10 * len(workspace.people)


def test_live_controls_deliver_a_burst_using_fixture_data(project, monkeypatch):
    import streamlit as st
    original = AdminService.deliver_one
    delivered = []

    def one_burst(service, *args, **kwargs):
        record = original(service, *args, **kwargs)
        delivered.append(record)
        if len(delivered) == 12:
            st.session_state.live_running = False
        return record

    monkeypatch.setattr(AdminService, "deliver_one", one_burst)
    app = admin_app("Live")
    app.select_slider[0].set_value(0.0)
    next(b for b in app.button if b.label == "Start").click().run()
    assert not app.exception and not app.error
    assert len(delivered) == 12
    assert app.session_state["live_rounds"] == 12
    assert len(app.session_state["live_feed"]) == 10
    assert len(json.loads((project / "data/generated_emails.json").read_text())["emails"]) == 12


def test_real_data_pages_render_without_writes():
    def fingerprint():
        return {p.name: (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
                for p in (ROOT / "data").iterdir() if p.is_file()}

    before = fingerprint()
    trainee = AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()
    assert not trainee.exception and not trainee.error
    app = admin_app()
    for section in ("Dashboard", "Live", "Person", "All history", "Run", "Model", "Emails", "System"):
        app.radio(key="admin_section").set_value(section).run()
        assert not app.exception, section
        # Person uses a red verdict for an incorrect human answer; that is
        # expected content, not a renderer failure.
        assert all(e.value.startswith("Said **") for e in app.error), section
    assert fingerprint() == before


@pytest.mark.parametrize("entry", ["live", "run"])
@pytest.mark.parametrize("legacy_flag", [True, False])
def test_admin_answers_never_use_hidden_probabilities_even_with_old_flags(workspace, monkeypatch, entry, legacy_flag):
    from backend.human import SimulatedHuman
    from backend.reader import RuleReader
    seed_training(workspace)
    for person in workspace.people:
        person.hidden_probs = None  # Any probability lookup would fail.

    def forbidden(*args, **kwargs):
        raise AssertionError("Admin must use the email reader directly")

    monkeypatch.setattr(SimulatedHuman, "respond", forbidden)
    service = authorized_service(workspace.root)
    if entry == "live":
        record = service.deliver_one(workspace, use_reader=legacy_flag, build_new=False)
        assert record is not None
        assert record["action"] in ("click", "report", "ignore")
    else:
        assert service.run_many(workspace, 2, use_reader=legacy_flag, build_new=False) == (2, 0)
    assert all(isinstance(service._engine(workspace, legacy_flag).answerer_for(p.id), RuleReader)
               for p in workspace.people)


@pytest.mark.parametrize("label", ["phishing", "legitimate"])
def test_legacy_human_interface_inspects_email_without_hidden_values_or_random_draws(monkeypatch, label):
    from types import SimpleNamespace
    from backend.human import SimulatedHuman
    from backend.reader import RuleReader
    person = SimpleNamespace(security_awareness="high")  # No hidden_probs field.
    email = {"label": label, "cue": "it_login", "subject": "Account review",
             "sender_email": "sender@outside.example", "body": "Please review the notice."}

    def forbidden():
        raise AssertionError("Answers must not be selected by a random probability draw")

    monkeypatch.setattr("random.random", forbidden)
    expected = RuleReader(person).respond(email)
    assert SimulatedHuman(person).respond(email) == expected


def test_command_line_answerers_always_use_reader_even_for_legacy_false_flag(workspace, monkeypatch):
    import main
    import live
    from backend.human import SimulatedHuman
    from backend.reader import RuleReader
    seed_training(workspace)
    person = workspace.people[0]
    person.hidden_probs = None

    def forbidden(*args, **kwargs):
        raise AssertionError("Command-line runners must use the email reader directly")

    monkeypatch.setattr(SimulatedHuman, "respond", forbidden)
    simulation = main.run_one(person, workspace.generator, workspace.twin, 2,
                              verbose=False, use_reader=False, generated=workspace.generated)
    assert isinstance(simulation.human, RuleReader) and len(simulation.rounds) == 2
    monkeypatch.chdir(workspace.root)
    runner = live.LiveRun(speed=0, plain=True, save_every=0)
    try:
        for staff in runner.people:
            staff.hidden_probs = None
            assert isinstance(runner.humans[staff.id], RuleReader)
        assert runner.step() is not None
    finally:
        runner.workspace.close()


def test_stale_browser_setting_cannot_restore_probability_answers(project, monkeypatch):
    from backend.human import SimulatedHuman

    def forbidden(*args, **kwargs):
        raise AssertionError("A stale browser flag must not restore probability answers")

    monkeypatch.setattr(SimulatedHuman, "respond", forbidden)
    app = admin_app("Run")
    app.session_state["use_reader"] = False
    app.run()
    assert not any(toggle.label == "Read the email" for toggle in app.toggle)
    assert any("hidden probabilities are not used" in caption.value for caption in app.caption)
    app.number_input[0].set_value(2)
    next(button for button in app.button if button.label == "Run now").click().run()
    assert not app.exception and not app.error
    records = [json.loads(line) for line in (project / "data/history_log.jsonl").read_text().splitlines()]
    assert len(records) == 2 and all(record["source"] == "sim" for record in records)


def test_manual_answers_use_only_the_submitted_choice_without_a_reader(workspace, monkeypatch):
    from backend.reader import RuleReader
    seed_training(workspace)

    def forbidden(*args, **kwargs):
        raise AssertionError("Manual answers must not be chosen by an automatic reader")

    monkeypatch.setattr(RuleReader, "respond", forbidden)
    first, second = workspace.people[:2]
    first.hidden_probs = second.hidden_probs = None
    email = workspace.generated[0]
    submit_answer(workspace, first.id, email["id"], False)
    submit_answer(workspace, second.id, email["id"], True)
    one, two = workspace.twin.get_history(first.id)[-1], workspace.twin.get_history(second.id)[-1]
    assert one["said"] == "not spam" and two["said"] == "spam"
    assert one["source"] == two["source"] == "app"

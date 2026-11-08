"""Admin operations run exclusively against pytest temporary directories."""

import hashlib
import json
from pathlib import Path
import sqlite3
import zipfile

import pytest

from backend.admin import AdminService, DB_OBJECTS, verify_password
from backend.auth import AdminAuthority


@pytest.fixture
def service(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "hospital_people.json").write_text(json.dumps({"people": [
        {"job_id": "P01", "name": "Test", "job_title": "Nurse", "simulation": {}}
    ]}))
    email = {"id": 1, "label": "phishing", "cue": "urgency", "subject": "Test",
             "body": "Example", "sender_email": "test@hospital.example"}
    (data / "hospital_emails_mixed.json").write_text(json.dumps({"emails": [email]}))
    rec = {"person_id": "P01", "email_id": 1, "label": "phishing", "cue": "urgency",
           "key": "urgency", "action": "report", "yes": 0, "no": 1,
           "p_before": 0, "p_click": 0, "subject": "Test", "source": "sim",
           "n": 1, "time": "2026-11-03T12:00:00", "correct": True}
    (data / "history_log.jsonl").write_text(json.dumps(rec) + "\n")
    (data / "responses.json").write_text("[]")
    authority = AdminAuthority(lambda: "fixture-secret", "fixture-session")
    token = authority.login("fixture-secret")
    return AdminService(tmp_path, authority, lambda: token)


def read_audit(service):
    return [json.loads(line) for line in (service.data / "admin_audit.jsonl").read_text().splitlines()]


def test_password_fails_closed_and_handles_unicode():
    for configured in (None, "", "   ", 123):
        assert not verify_password("", configured)
    assert not verify_password("wrong", "secret")
    assert verify_password("sëcret", "sëcret")


def test_integrity_reports_malformed_unknown_duplicate_and_missing(service):
    email_file = service.data / "hospital_emails_mixed.json"
    email = json.loads(email_file.read_text())["emails"][0]
    (service.data / "generated_emails.json").write_text(json.dumps({"emails": [email]}))
    log = service.data / "history_log.jsonl"
    with log.open("a") as stream:
        stream.write('{broken\n')
        stream.write(json.dumps({"person_id": "missing", "email_id": 999}) + "\n")
        stream.write('[]\n')
    report = service.integrity()
    assert report["records_read"] == 4
    assert report["json_objects"] == 2
    assert report["counts"] == {"duplicate_email_id": 1, "malformed_jsonl": 1,
                                "missing_fields": 1, "unknown_person_id": 1,
                                "unknown_email_id": 1, "invalid_record": 1}


def test_integrity_clean_and_optional_files_missing(service):
    assert service.integrity()["issues"] == []
    before = sorted(service.root.rglob("*"))
    rows = service.file_status()
    assert next(r for r in rows if r["file"] == "history_log.jsonl")["records"] == 1
    assert next(r for r in rows if r["file"] == "responses.json")["records"] == 0
    assert not next(r for r in rows if r["file"] == "simulation.db")["exists"]
    assert all(r["error"] == "Database missing" for r in service.database_status())
    assert service.list_backups() == []
    assert sorted(service.root.rglob("*")) == before


def test_database_status_all_tables_and_views_is_read_only(service):
    path = service.data / "simulation.db"
    with sqlite3.connect(path) as conn:
        conn.executescript((Path(__file__).parents[1] / "database/schema.sql").read_text())
    original = path.read_bytes()
    rows = service.database_status()
    assert {r["object"] for r in rows} == set(DB_OBJECTS)
    assert all(r["rows"] == 0 and not r["error"] for r in rows)
    assert path.read_bytes() == original


def test_backup_restore_round_trip_preserves_audit_and_prebackup(service):
    original = {p.name: p.read_bytes() for p in service.data.iterdir()}
    backup = service.create_backup()
    (service.data / "responses.json").write_text('[{"new": true}]')
    (service.data / "generated_emails.json").write_text('{"emails": []}')
    changed = (service.data / "responses.json").read_bytes()
    result = service.restore_backup(backup["name"], "RESTORE")
    assert len(service.list_backups()) == 2
    for name, content in original.items():
        assert (service.data / name).read_bytes() == content
    assert not (service.data / "generated_emails.json").exists()
    assert service._read_backup(result["pre_restore_backup"])["responses.json"] == changed
    audit = read_audit(service)
    assert [r["outcome"] for r in audit] == ["started", "success", "started", "success"]
    assert audit[-1]["action"] == "restore"
    assert audit[-1]["counts_affected"] > 0
    assert all({"timestamp", "action", "target", "counts_affected", "outcome"} <= r.keys()
               for r in audit)
    assert not service.lock_path.exists()


def test_confirmation_and_active_jobs_block_writes(service):
    with pytest.raises(ValueError, match="RESTORE"):
        service.restore_backup("alert-test.zip", "no")
    for action in (lambda: service.create_backup(active_job=True),
                   lambda: service.restore_backup("alert-test.zip", "RESTORE", active_job=True),
                   lambda: service.clear_caches(lambda: None, lambda: None, active_job=True)):
        with pytest.raises(RuntimeError, match="Live or Run"):
            action()
    assert not service.backups.exists()
    assert not (service.data / "admin_audit.jsonl").exists()


def test_exclusive_lock_and_failed_audit(service):
    service.lock_path.write_text("busy")
    with pytest.raises(RuntimeError, match="holds"):
        service.create_backup()
    service.lock_path.unlink()
    with pytest.raises(FileNotFoundError):
        service.restore_backup("alert-missing.zip", "RESTORE")
    assert read_audit(service)[-1]["outcome"] == "failed"
    assert not service.lock_path.exists()


@pytest.mark.parametrize("member", ["../outside.txt", "data/../outside.txt", ".streamlit/secrets.toml"])
def test_restore_rejects_unsafe_members_before_changes(service, member):
    service.backups.mkdir()
    target = service.backups / "alert-unsafe.zip"
    with zipfile.ZipFile(target, "w") as archive:
        archive.writestr(member, "bad")
        archive.writestr("manifest.json", json.dumps({"version": 1, "files": {
            member: hashlib.sha256(b"bad").hexdigest()}}))
    before = (service.data / "history_log.jsonl").read_bytes()
    with pytest.raises(ValueError, match="unexpected file paths"):
        service.restore_backup(target.name, "RESTORE")
    assert (service.data / "history_log.jsonl").read_bytes() == before
    assert len(service.list_backups()) == 1


def test_restore_rejects_corrupt_checksum_and_sqlite_sidecars(service):
    backup = service.create_backup()
    payload = service._read_backup(backup["name"])
    assert "history_log.jsonl" in payload
    (service.data / "simulation.db-wal").write_bytes(b"busy")
    with pytest.raises(RuntimeError, match="sidecar"):
        service.restore_backup(backup["name"], "RESTORE")
    assert len(service.list_backups()) == 1
    (service.data / "simulation.db-wal").unlink()
    target = service.backups / "alert-corrupt.zip"
    with zipfile.ZipFile(target, "w") as archive:
        files = {}
        for name in ("responses.json", "hospital_people.json", "hospital_emails_mixed.json"):
            content = (service.data / name).read_bytes()
            archive.writestr("data/" + name, content)
            files["data/" + name] = hashlib.sha256(content).hexdigest()
        files["data/responses.json"] = "incorrect"
        archive.writestr("manifest.json", json.dumps({"version": 1, "files": files}))
    with pytest.raises(ValueError, match="Checksum mismatch"):
        service.restore_backup(target.name, "RESTORE")


def test_cache_clear_audited(service):
    called = []
    service.clear_caches(lambda: called.append("data"), lambda: called.append("resources"))
    assert called == ["data", "resources"]
    assert read_audit(service)[-1]["action"] == "clear_caches"
    assert read_audit(service)[-1]["outcome"] == "success"


def test_failed_cache_clear_is_not_recorded_as_success(service):
    def fail():
        raise RuntimeError("cache failure")

    with pytest.raises(RuntimeError, match="cache failure"):
        service.clear_caches(fail, lambda: None)
    assert read_audit(service)[-1]["outcome"] == "failed"


def test_generated_csv_collisions_and_snapshot_counts(service):
    (service.data / "generated_emails.csv").write_text("ID,Subject,Body\n1,Duplicate,Example\n")
    (service.data / "people_history.json").write_text(json.dumps({
        "note": "Snapshot", "updated": "today", "people": {"P01": {}}}))
    assert service.integrity()["counts"] == {"duplicate_email_id": 1}
    assert next(r for r in service.file_status()
                if r["file"] == "people_history.json")["records"] == 1


def test_restore_rolls_back_on_replace_failure(service, monkeypatch):
    import backend.admin as admin
    backup = service.create_backup()
    responses = service.data / "responses.json"
    responses.write_text('[{"keep": true}]')
    before = responses.read_bytes()
    original = admin._atomic_bytes
    failed = False

    def fail_once(path, data):
        nonlocal failed
        if path == responses and not failed:
            failed = True
            raise OSError("simulated write failure")
        return original(path, data)

    monkeypatch.setattr(admin, "_atomic_bytes", fail_once)
    with pytest.raises(OSError, match="simulated"):
        service.restore_backup(backup["name"], "RESTORE")
    assert responses.read_bytes() == before
    assert read_audit(service)[-1]["outcome"] == "failed"


def test_login_and_authenticated_page_read_real_data_without_writes():
    """Only render; never click write controls on the real repository."""
    from streamlit.testing.v1 import AppTest
    root = Path(__file__).resolve().parents[1]
    data = root / "data"
    before = {p.name: (p.stat().st_size, p.stat().st_mtime_ns)
              for p in data.iterdir() if p.is_file()}
    app = AppTest.from_file(str(root / "app.py")).run().switch_page("pages/admin.py")
    app.secrets["admin_password"] = "test-only-secret"
    app.run()
    assert not app.exception
    assert len(app.dataframe) == 0
    app.text_input[0].set_value("incorrect")
    app.button[0].click().run()
    assert not app.exception
    assert len(app.dataframe) == 0
    app.text_input[0].set_value("test-only-secret")
    app.button[0].click().run()
    assert not app.exception
    app.radio(key="admin_section").set_value("System").run()
    assert len(app.dataframe) >= 2
    assert not app.error
    after = {p.name: (p.stat().st_size, p.stat().st_mtime_ns)
             for p in data.iterdir() if p.is_file()}
    assert before == after


def test_page_without_configured_password_is_locked():
    from streamlit.testing.v1 import AppTest
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run().switch_page("pages/admin.py")
    app.secrets["admin_password"] = ""
    app.run()
    assert not app.exception
    assert len(app.dataframe) == 0
    assert app.button[0].disabled


def test_admin_page_blocks_live_and_run_jobs(service, monkeypatch):
    from streamlit.testing.v1 import AppTest
    import backend.admin as admin
    monkeypatch.setattr(admin, "AdminService", lambda *args, **kwargs: service)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run().switch_page("pages/admin.py")
    app.secrets["admin_password"] = "test-secret"
    app.session_state["admin_session_id"] = "test-session"
    app.session_state["admin_auth_token"] = AdminAuthority(
        lambda: "test-secret", "test-session").login("test-secret")
    app.session_state["admin_section"] = "System"
    for flag in ("live_running", "run_running"):
        app.session_state[flag] = True
        app.run()
        assert not app.exception
        assert any("active" in error.value for error in app.error)
        assert all(b.disabled for b in app.button if b.label != "Log out")
        app.session_state[flag] = False
    assert not (service.data / "admin_audit.jsonl").exists()


def test_admin_page_backup_restore_on_fixture_data(service, monkeypatch):
    from streamlit.testing.v1 import AppTest
    import backend.admin as admin
    monkeypatch.setattr(admin, "AdminService", lambda *args, **kwargs: service)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run().switch_page("pages/admin.py")
    app.secrets["admin_password"] = "test-secret"
    app.session_state["admin_session_id"] = "test-session"
    app.session_state["admin_auth_token"] = AdminAuthority(
        lambda: "test-secret", "test-session").login("test-secret")
    app.session_state["admin_section"] = "System"
    app.run()
    next(b for b in app.button if b.label == "Create backup").click().run()
    assert not app.exception and not app.error
    responses = service.data / "responses.json"
    responses.write_text('[{"new": true}]')
    app.text_input(key="admin_restore_confirmation").set_value("RESTORE")
    next(b for b in app.button if b.label == "Restore selected backup").click().run()
    assert not app.exception and not app.error
    assert responses.read_text() == "[]"
    assert len(service.list_backups()) == 2
    assert read_audit(service)[-1]["action"] == "clear_caches"


def test_one_failed_section_does_not_hide_remaining_sections(service, monkeypatch):
    from streamlit.testing.v1 import AppTest
    import backend.admin as admin
    monkeypatch.setattr(admin, "AdminService", lambda *args, **kwargs: service)

    def fail():
        raise RuntimeError("broken database fixture")

    monkeypatch.setattr(service, "database_status", fail)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run().switch_page("pages/admin.py")
    app.secrets["admin_password"] = "test-secret"
    app.session_state["admin_session_id"] = "test-session"
    app.session_state["admin_auth_token"] = AdminAuthority(
        lambda: "test-secret", "test-session").login("test-secret")
    app.session_state["admin_section"] = "System"
    app.run()
    assert not app.exception
    assert any("broken database fixture" in e.value for e in app.error)
    assert any(b.label == "Create backup" for b in app.button)
    assert any(b.label == "Clear data and resource caches" for b in app.button)

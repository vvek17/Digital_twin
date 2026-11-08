"""Admin operations. All paths are relative to an explicit project root.

Reads never build a database or repair a file. The lock serializes admin
writes only; existing simulation writers do not participate in this lock.
"""

from collections import Counter
from contextlib import contextmanager
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import uuid
from functools import wraps

from backend.auth import verify_password
import zipfile


DATA_FILES = (
    "hospital_people.json", "hospital_emails_mixed.json", "history_log.jsonl",
    "people_history.json", "simulation.db", "responses.json",
    "generated_emails.json", "history.csv", "results.csv", "scores.csv",
    "email_scores.csv", "click_rates.csv", "person_summary.csv",
    "generated_emails.csv", "db_emails.json", "new_emails.json", "types.csv",
    "admin_audit.jsonl",
    "practice_sessions.json",
)
DB_OBJECTS = ("emails", "red_flags", "people", "hidden_probs", "deliveries",
              "v_person_scores", "v_email_scores", "v_cue_rates")
HISTORY_FIELDS = ("person_id", "email_id", "label", "cue", "key", "action",
                  "yes", "no", "p_before", "p_click", "subject", "source",
                  "n", "time", "correct")


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def admin_only(method):
    @wraps(method)
    def guarded(self, *args, **kwargs):
        self.require_admin()
        return method(self, *args, **kwargs)
    return guarded


def _atomic_bytes(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".admin-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class AdminService:
    def __init__(self, root, authority=None, token_provider=None, job_provider=None):
        self.authority = authority
        self.token_provider = token_provider or (lambda: None)
        self.job_provider = job_provider or (lambda: False)
        self.root = Path(root).resolve()
        self.data = self.root / "data"
        self.backups = self.root / "backups"
        self.lock_path = self.root / ".admin.lock"

    def require_admin(self):
        if self.authority is None:
            raise PermissionError("Admin login is required")
        self.authority.require(self.token_provider())

    def _path(self, name):
        path = self.data / name
        if path.is_symlink() or path.resolve().parent != self.data.resolve():
            raise ValueError("Admin operations do not follow data-file symlinks")
        return path

    @admin_only
    def file_status(self):
        rows = []
        for name in DATA_FILES:
            row = {"file": name, "exists": False, "bytes": None,
                   "modified_utc": None, "records": None, "error": ""}
            try:
                path = self._path(name)
                row["exists"] = path.is_file()
                if row["exists"]:
                    info = path.stat()
                    row.update(bytes=info.st_size, modified_utc=datetime.fromtimestamp(
                        info.st_mtime, timezone.utc).isoformat())
                    if path.suffix == ".jsonl":
                        with path.open() as stream:
                            row["records"] = sum(bool(line.strip()) for line in stream)
                    elif path.suffix == ".csv":
                        with path.open(newline="") as stream:
                            reader = csv.reader(stream)
                            next(reader, None)
                            row["records"] = sum(1 for _ in reader)
                    elif path.suffix == ".json":
                        value = json.loads(path.read_text())
                        key = {"hospital_people.json": "people",
                               "people_history.json": "people",
                               "hospital_emails_mixed.json": "emails",
                               "generated_emails.json": "emails", "practice_sessions.json": "sessions",
                               "db_emails.json": "emails",
                               "new_emails.json": "emails"}.get(name)
                        if key:
                            value = value[key]
                        row["records"] = len(value) if isinstance(value, (dict, list)) else None
                    elif path.suffix == ".db":
                        row["records"] = sum(r["rows"] or 0 for r in
                                             self.database_status() if r["kind"] == "table")
            except Exception as exc:
                row["error"] = str(exc)
            rows.append(row)
        return rows

    @admin_only
    def database_status(self):
        path = self._path("simulation.db")
        if not path.is_file():
            return [{"object": name, "kind": "view" if name.startswith("v_") else "table",
                     "rows": None, "error": "Database missing"} for name in DB_OBJECTS]
        rows = []
        conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        try:
            for name in DB_OBJECTS:
                row = {"object": name, "kind": "view" if name.startswith("v_") else "table",
                       "rows": None, "error": ""}
                try:
                    row["rows"] = conn.execute('SELECT COUNT(*) FROM "%s"' % name).fetchone()[0]
                except sqlite3.Error as exc:
                    row["error"] = str(exc)
                rows.append(row)
        finally:
            conn.close()
        return rows

    @admin_only
    def integrity(self):
        issues, people, emails = [], set(), set()
        seen_emails = {}
        email_contents = {}

        def issue(file, record, kind, detail):
            issues.append({"file": file, "record": record, "kind": kind, "detail": detail})

        for name, key, required in (
            ("hospital_people.json", "people", ("job_id", "name", "job_title", "simulation")),
            ("hospital_emails_mixed.json", "emails", ("id", "label", "cue", "subject", "body", "sender_email")),
            ("generated_emails.json", "emails", ("id", "label", "cue", "subject", "body", "sender_email")),
        ):
            path = self._path(name)
            if not path.exists() and name == "generated_emails.json":
                continue
            try:
                records = json.loads(path.read_text())[key]
                if not isinstance(records, list):
                    raise ValueError("%s must be a list" % key)
                for pos, rec in enumerate(records, 1):
                    if not isinstance(rec, dict):
                        issue(name, pos, "invalid_record", "Expected an object")
                        continue
                    missing = [f for f in required if f not in rec]
                    if missing:
                        issue(name, pos, "missing_fields", ", ".join(missing))
                    identity = rec.get("job_id" if key == "people" else "id")
                    if not isinstance(identity, (str, int)) or isinstance(identity, bool):
                        issue(name, pos, "invalid_id", repr(identity))
                        continue
                    if key == "people":
                        if identity in people:
                            issue(name, pos, "duplicate_person_id", str(identity))
                        people.add(identity)
                    else:
                        if identity in seen_emails:
                            issue(name, pos, "duplicate_email_id", "%s also in %s" % (
                                identity, seen_emails[identity]))
                        seen_emails[identity] = name
                        email_contents[identity] = rec
                        emails.add(identity)
            except Exception as exc:
                issue(name, None, "unreadable_source", str(exc))

        from backend.practice import load_sessions, PRACTICE_FILE
        try:
            for session in load_sessions(self.data):
                if session["person_id"] not in people:
                    issue(PRACTICE_FILE, session["id"], "unknown_person_id", str(session["person_id"]))
                for email in session["emails"]:
                    identity = email["id"]
                    existing = email_contents.get(identity)
                    if existing and any(existing.get(key) != email.get(key)
                                        for key in ("subject", "body", "label", "cue")):
                        issue(PRACTICE_FILE, session["id"], "conflicting_email_id", str(identity))
                    email_contents[identity] = email
                    seen_emails.setdefault(identity, PRACTICE_FILE)
                    emails.add(identity)
        except Exception as exc:
            issue(PRACTICE_FILE, None, "unreadable_source", str(exc))

        # New Studio CSV rows mirror the shared pool. Legacy CLI CSV rows may
        # have separate IDs; accept matching exports but report conflicts.
        csv_path = self._path("generated_emails.csv")
        if csv_path.exists():
            try:
                csv_ids = set()
                with csv_path.open(newline="") as stream:
                    for pos, rec in enumerate(csv.DictReader(stream), 2):
                        identity = rec.get("ID")
                        if not identity:
                            issue(csv_path.name, pos, "missing_fields", "ID")
                            continue
                        try:
                            identity = int(identity)
                        except ValueError:
                            pass
                        existing = email_contents.get(identity)
                        exported_copy = (existing is not None
                                         and existing.get("subject") == rec.get("Subject")
                                         and existing.get("body") == rec.get("Body")
                                         and (rec.get("Email Type") is None
                                              or rec["Email Type"] == (existing.get("technique") or "")))
                        if identity in csv_ids or (identity in seen_emails and not exported_copy):
                            issue(csv_path.name, pos, "duplicate_email_id", "%s also in %s" % (
                                identity, seen_emails[identity]))
                        seen_emails[identity] = csv_path.name
                        csv_ids.add(identity)
                        emails.add(identity)
            except Exception as exc:
                issue(csv_path.name, None, "unreadable_source", str(exc))

        path = self._path("history_log.jsonl")
        read = valid = 0
        if path.exists():
            with path.open() as stream:
                for line_no, line in enumerate(stream, 1):
                    if not line.strip():
                        continue
                    read += 1
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError as exc:
                        issue(path.name, line_no, "malformed_jsonl", str(exc))
                        continue
                    if not isinstance(rec, dict):
                        issue(path.name, line_no, "invalid_record", "Expected an object")
                        continue
                    valid += 1
                    missing = [f for f in HISTORY_FIELDS if f not in rec]
                    if missing:
                        issue(path.name, line_no, "missing_fields", ", ".join(missing))
                    for field, known, kind in (("person_id", people, "unknown_person_id"),
                                                ("email_id", emails, "unknown_email_id")):
                        value = rec.get(field)
                        if not isinstance(value, (str, int)) or value not in known:
                            issue(path.name, line_no, kind, repr(value))
        return {"records_read": read, "json_objects": valid, "issues": issues,
                "counts": dict(Counter(i["kind"] for i in issues))}

    @contextmanager
    def write_operation(self, action, target, active_job=False):
        """Exclusive admin lock, with audit entries for completed/failed writes."""
        self.require_admin()
        if active_job or (action not in {"simulate_live", "simulate_batch", "save_simulation"}
                          and self.job_provider()):
            raise RuntimeError("Stop the Live or Run job before admin writes")
        self.root.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise RuntimeError("Another admin operation holds .admin.lock. If a process crashed, "
                               "verify it has stopped before removing the stale lock.") from None
        try:
            with os.fdopen(fd, "w") as stream:
                stream.write("pid=%d time=%s\n" % (os.getpid(), utc_now()))
            # Check that auditing works before changing managed data.
            self.audit(action, target, 0, "started")
            result = {"counts_affected": 0}
            try:
                yield result
            except Exception as exc:
                self.audit(action, target, result["counts_affected"], "failed", str(exc))
                raise
            else:
                self.audit(action, target, result["counts_affected"], "success", result.get("detail", ""))
        finally:
            self.lock_path.unlink()

    @admin_only
    def audit(self, action, target, counts, outcome, detail=""):
        path = self._path("admin_audit.jsonl")
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {"timestamp": utc_now(), "action": action, "target": str(target),
                  "counts_affected": counts, "outcome": outcome, "detail": detail}
        with path.open("a") as stream:
            stream.write(json.dumps(record) + "\n")
            stream.flush()
            os.fsync(stream.fileno())

    @admin_only
    def _backup(self):
        """Called under the admin lock; simulation writers must be stopped."""
        for filename in ("simulation.db-wal", "simulation.db-shm", "simulation.db-journal"):
            if (self.data / filename).exists():
                raise RuntimeError("SQLite sidecar files exist. Stop database users before backup/restore.")
        self.backups.mkdir(parents=True, exist_ok=True)
        name = "alert-%s-%s.zip" % (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"),
                                    uuid.uuid4().hex[:8])
        target = self.backups / name
        manifest = {"version": 1, "created_at": utc_now(), "files": {}}
        # Serialize once so checksums describe exactly the archived bytes.
        content = io.BytesIO()
        with zipfile.ZipFile(content, "w", zipfile.ZIP_DEFLATED) as archive:
            for filename in DATA_FILES:
                path = self._path(filename)
                if path.is_file():
                    data = path.read_bytes()
                    member = "data/" + filename
                    archive.writestr(member, data)
                    manifest["files"][member] = hashlib.sha256(data).hexdigest()
            archive.writestr("manifest.json", json.dumps(manifest, indent=2))
        _atomic_bytes(target, content.getvalue())
        return {"name": name, "files": len(manifest["files"]), "bytes": target.stat().st_size}

    @admin_only
    def create_backup(self, active_job=False):
        with self.write_operation("backup", "data", active_job) as operation:
            result = self._backup()
            operation["counts_affected"] = result["files"]
            return result

    @admin_only
    def list_backups(self):
        if not self.backups.exists():
            return []
        return [{"name": p.name, "bytes": p.stat().st_size,
                 "modified_utc": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat()}
                for p in sorted(self.backups.glob("alert-*.zip"), reverse=True) if not p.is_symlink()]

    @admin_only
    def _read_backup(self, name):
        if Path(name).name != name or not name.startswith("alert-") or not name.endswith(".zip"):
            raise ValueError("Choose a listed ALERT backup")
        path = self.backups / name
        if path.is_symlink():
            raise ValueError("Backup symlinks are not allowed")
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            if len(names) != len(set(names)) or "manifest.json" not in names:
                raise ValueError("Invalid or duplicate backup members")
            if sum(i.file_size for i in archive.infolist()) > 1024 ** 3:
                raise ValueError("Backup exceeds the 1 GiB restore limit")
            manifest = json.loads(archive.read("manifest.json"))
            files = manifest.get("files")
            allowed = {"data/" + n for n in DATA_FILES}
            if (manifest.get("version") != 1 or not isinstance(files, dict)
                    or not set(files).issubset(allowed)
                    or set(names) != set(files) | {"manifest.json"}):
                raise ValueError("Unsupported backup manifest or unexpected file paths")
            if not {"data/hospital_people.json", "data/hospital_emails_mixed.json"} <= set(files):
                raise ValueError("Backup must contain both authored source files")
            payload = {}
            for member, digest in files.items():
                data = archive.read(member)
                if hashlib.sha256(data).hexdigest() != digest:
                    raise ValueError("Checksum mismatch: " + member)
                payload[Path(member).name] = data
            return payload

    @admin_only
    def restore_backup(self, name, confirmation, active_job=False):
        if confirmation != "RESTORE":
            raise ValueError("Type RESTORE to confirm replacement of the data files")
        with self.write_operation("restore", name, active_job) as operation:
            payload = self._read_backup(name)
            # Validate all destination paths before creating a backup or replacing files.
            paths = {n: self._path(n) for n in DATA_FILES if n != "admin_audit.jsonl"}
            for filename in ("simulation.db-wal", "simulation.db-shm", "simulation.db-journal"):
                if (self.data / filename).exists():
                    raise RuntimeError("SQLite sidecar files exist. Stop database users before restore.")
            before = self._backup()
            rollback = self._read_backup(before["name"])
            try:
                for filename, path in paths.items():
                    if filename in payload:
                        _atomic_bytes(path, payload[filename])
                        operation["counts_affected"] += 1
                    elif path.exists():
                        path.unlink()
                        operation["counts_affected"] += 1
            except Exception:
                for filename, path in paths.items():
                    if filename in rollback:
                        _atomic_bytes(path, rollback[filename])
                    elif path.exists():
                        path.unlink()
                raise
            # Never replace the current audit trail with the older archived one.
            return {"restored": name, "pre_restore_backup": before["name"],
                    "files": len([n for n in payload if n != "admin_audit.jsonl"])}

    @admin_only
    def clear_caches(self, clear_data, clear_resources, active_job=False):
        """UI supplies Streamlit callbacks; backend owns the write guard and audit."""
        with self.write_operation("clear_caches", "Streamlit data and resources", active_job):
            clear_data()
            clear_resources()

    @admin_only
    def reset_all_results(self, confirmation, active_job=False):
        """Explicit, backed-up reset. Authored sources and the audit trail survive."""
        if confirmation.strip().upper() != "RESET ALL RESULTS":
            raise ValueError("Type RESET ALL RESULTS to confirm clearing all saved results")
        from backend.persona import load_people
        from backend.twin import TwinPredictor, CSV_COLUMNS, RESULTS_COLUMNS
        from backend.email_generator import CSV_COLUMNS as GENERATED_COLUMNS
        from database.build import build

        reset_files = ("history_log.jsonl", "responses.json", "generated_emails.json",
                       "generated_emails.csv", "people_history.json", "simulation.db",
                       "history.csv", "results.csv", "scores.csv", "email_scores.csv",
                       "click_rates.csv", "person_summary.csv", "db_emails.json", "new_emails.json",
                       "practice_sessions.json")
        with self.write_operation("reset_all_results", "all experiment and training results", active_job) as operation:
            paths = {name: self._path(name) for name in reset_files}
            log = paths["history_log.jsonl"]
            records = sum(bool(line.strip()) for line in log.read_bytes().splitlines()) if log.exists() else 0
            # Build the replacement projection and exports in isolation before
            # touching current results. The twin's learning implementation is unchanged.
            with tempfile.TemporaryDirectory(prefix="alert-reset-") as folder:
                stage = Path(folder)
                for name in ("hospital_people.json", "hospital_emails_mixed.json"):
                    (stage / name).write_bytes(self._path(name).read_bytes())
                (stage / "history_log.jsonl").write_bytes(b"")
                (stage / "responses.json").write_text("[]\n")
                (stage / "practice_sessions.json").write_text('{"version": 1, "sessions": []}\n')
                (stage / "generated_emails.json").write_text(json.dumps({
                    "note": "Fresh manual-training start; previous results are backed up.",
                    "count": 0, "emails": []}) + "\n")
                for name, columns in (("history.csv", CSV_COLUMNS), ("results.csv", RESULTS_COLUMNS),
                                      ("generated_emails.csv", GENERATED_COLUMNS)):
                    with (stage / name).open("w", newline="") as stream:
                        csv.writer(stream).writerow(columns)
                people = load_people(str(stage / "hospital_people.json"))
                twin = TwinPredictor(log_path=None, csv_path=None, results_path=None,
                                     people_by_id={p.id: p for p in people})
                for person in people:
                    twin.get_totals(person.id)
                twin.save(str(stage / "people_history.json"), twin.people_by_id, export_dir=str(stage))
                twin.write_email_scores({}, str(stage / "email_scores.csv"))
                build(str(stage / "simulation.db"), data_dir=stage)
                replacements = {name: (stage / name).read_bytes() for name in reset_files
                                if (stage / name).exists()}

            backup = self._backup()
            original = self._read_backup(backup["name"])
            try:
                for name, path in paths.items():
                    if name in replacements:
                        _atomic_bytes(path, replacements[name])
                    elif path.exists():
                        path.unlink()
            except Exception:
                for name, path in paths.items():
                    if name in original:
                        _atomic_bytes(path, original[name])
                    elif path.exists():
                        path.unlink()
                raise
            operation["counts_affected"] = records
            operation["detail"] = json.dumps({"backup": backup["name"], "files": len(reset_files)})
            return {"records_cleared": records, "backup": backup["name"]}

    @admin_only
    def load_workspace(self):
        from backend.training import Workspace
        return Workspace(self.root)

    @admin_only
    def assign_practice(self, workspace, person_id, count, request_id, on_progress=None):
        """Assign exactly this many in-app emails, without answering any of them."""
        from backend.training import Workspace
        from backend.practice import (MAX_PRACTICE_EMAILS, PRACTICE_FILE, current_session,
                                      prepare_emails, session_records)
        self._check_workspace(workspace)
        if type(count) is not int or not 1 <= count <= MAX_PRACTICE_EMAILS:
            raise ValueError("Practice count must be a whole number between 1 and 1,000,000")
        if not isinstance(request_id, str) or not 8 <= len(request_id) <= 128:
            raise ValueError("A valid practice request ID is required")
        with self.write_operation("assign_practice", str(person_id)) as operation:
            fresh = Workspace(self.root)
            try:
                if (not isinstance(person_id, (str, int)) or isinstance(person_id, bool)
                        or person_id not in fresh.people_by_id):
                    raise ValueError("Unknown practice participant")
                for previous in fresh.practice_sessions:
                    if previous["request_id"] == request_id:
                        if previous["person_id"] != person_id or previous["count"] != count:
                            raise ValueError("This request ID was already used for a different assignment")
                        return previous
                previous = current_session(fresh, person_id)
                if previous:
                    answered = {record["email_id"] for record in session_records(fresh, previous)}
                    if len(answered) < previous["count"]:
                        raise ValueError("This person already has unfinished practice (%d of %d answered). "
                                         "Complete it before assigning another session."
                                         % (len(answered), previous["count"]))
                emails = prepare_emails(fresh, person_id, count, on_progress)
                self.require_admin()
                session = {"id": uuid.uuid4().hex, "request_id": request_id,
                           "person_id": person_id, "count": count, "created_utc": utc_now(), "emails": emails}
                # One atomic file stores the assignment and complete email snapshots.
                # Failed preparation never leaves a shorter or half-written session.
                payload = {"version": 1, "sessions": fresh.practice_sessions + [session]}
                self.require_admin()
                _atomic_bytes(self._path(PRACTICE_FILE), (json.dumps(payload, indent=2) + "\n").encode())
                operation["counts_affected"] = count
                return session
            finally:
                fresh.close()

    def _check_workspace(self, workspace):
        self.require_admin()
        if workspace.root != self.root:
            raise ValueError("Workspace belongs to another project")

    def _sync_generated(self, workspace):
        """Keep an older Live/Run session from overwriting newer shared email data."""
        from backend import store
        from backend.practice import load_sessions, merge_session_emails
        sessions = load_sessions(workspace.data)
        stored = store.load_generated(str(workspace.data / "generated_emails.json"))
        workspace.generated[:] = merge_session_emails(workspace.generated, sessions, workspace.emails, stored)
        workspace.practice_sessions = sessions

    def _engine(self, workspace, use_reader=True, persist_generated=True):
        from itertools import count
        from backend import store
        from backend.engine import DeliveryEngine
        from backend.email_builder import EmailBuilder
        from backend.practice import next_dynamic_id
        from backend.reader import RuleReader
        self._check_workspace(workspace)
        self._sync_generated(workspace)
        identities = count(next_dynamic_id(workspace.emails, workspace.generated, workspace.data))
        # Keep the old use_reader argument compatible; it cannot enable hidden probabilities.
        answerers = {p.id: RuleReader(p) for p in workspace.people}
        def answerer_for(person_id):
            self.require_admin()
            return answerers[person_id]
        return DeliveryEngine(workspace.twin, workspace.people, workspace.emails,
                              answerer_for, workspace.generator,
                              EmailBuilder(workspace.generator), workspace.feedback,
                              next_id=identities.__next__,
                              on_generated=(lambda: store.save_generated(
                                  workspace.generated, str(workspace.data / "generated_emails.json")))
                              if persist_generated else None)

    @admin_only
    def deliver_one(self, workspace, use_reader=True, **options):
        self._check_workspace(workspace)
        with self.write_operation("simulate_live", "one delivery") as operation:
            record = self._engine(workspace, use_reader).deliver(
                generated=workspace.generated, **options)
            operation["counts_affected"] = int(record is not None)
            return record

    @admin_only
    def run_many(self, workspace, count, use_reader=True, **options):
        self._check_workspace(workspace)
        if not 1 <= int(count) <= 1000000:
            raise ValueError("Delivery count must be between 1 and 1,000,000")
        with self.write_operation("simulate_batch", "deliveries") as operation:
            engine = self._engine(workspace, use_reader, persist_generated=False)
            try:
                result = engine.deliver_many(int(count), generated=workspace.generated, **options)
            finally:
                # Retain complete messages even if a batch stops after some answers.
                # Do not rewrite the growing pool on every iteration of a large Run.
                from backend import store
                self.require_admin()
                store.save_generated(workspace.generated, str(workspace.data / "generated_emails.json"))
            operation["counts_affected"] = result[0]
            self._save_workspace(workspace, generated=True, email_scores=True)
            return result

    def _save_workspace(self, workspace, generated=False, email_scores=False):
        self._check_workspace(workspace)
        if generated:
            self._sync_generated(workspace)
        workspace.save(generated=generated)
        if email_scores:
            emails = {e["id"]: e for e in workspace.emails + workspace.generated}
            workspace.twin.write_email_scores(emails, str(workspace.data / "email_scores.csv"))

    @admin_only
    def save_workspace(self, workspace, generated=False, email_scores=False):
        with self.write_operation("save_simulation", "snapshot and exports"):
            self._save_workspace(workspace, generated, email_scores)

    @admin_only
    def generate_emails(self, workspace, count, technique=None):
        from backend.email_generator import EmailGeneratorLLM
        from backend import store
        from backend.practice import load_sessions, merge_session_emails, next_dynamic_id
        self._check_workspace(workspace)
        if not 1 <= int(count) <= 500:
            raise ValueError("Generate between 1 and 500 emails")
        with self.write_operation("generate_emails", technique or "Any") as operation:
            pool = merge_session_emails(store.load_generated(str(workspace.data / "generated_emails.json")),
                                        load_sessions(workspace.data), workspace.emails)
            identity = next_dynamic_id(workspace.emails, pool, workspace.data)
            maker = EmailGeneratorLLM(static=workspace.emails,
                                     csv_path=str(workspace.data / "generated_emails.csv"))
            made = []
            for _ in range(int(count)):
                self.require_admin()
                email = maker.generate(technique, save=False)
                if email:
                    email["id"] = identity
                    identity += 1
                    maker.append(email)
                    pool.append(email)
                    made.append(email)
                    operation["counts_affected"] += 1
            if made:
                store.save_generated(pool, str(workspace.data / "generated_emails.json"))
                workspace.generated[:] = pool
            return made, int(count) - len(made)

    @admin_only
    def generated_csv(self):
        path = self._path("generated_emails.csv")
        return path.read_text() if path.exists() else None

    @admin_only
    def compare_models(self, workspace, count, on_progress=None):
        from backend import benchmark
        from backend.email_builder import EmailBuilder
        from backend.ml_model import build_dataset, train_best
        self._check_workspace(workspace)
        if not 10 <= int(count) <= 2000:
            raise ValueError("Choose between 10 and 2,000 test emails")
        self._sync_generated(workspace)
        model, columns = train_best(build_dataset(
            str(workspace.data / "history_log.jsonl"), workspace.people,
            workspace.emails + workspace.generated))
        return benchmark.run(int(count), twin=workspace.twin, people=workspace.people,
                             model=model, feature_cols=columns, on_progress=on_progress,
                             builder=EmailBuilder(workspace.generator))

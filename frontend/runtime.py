"""Shared Streamlit session lifecycle; no experiment controls are rendered here."""

from pathlib import Path
import uuid

import streamlit as st

from backend.auth import AdminAuthority
from backend.training import Workspace
from database.db import Database


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class _SessionDatabase:
    """Keep a path in session state, never a thread-bound SQLite connection.

    Streamlit may run the next interaction on another script thread. Database
    queries already return materialized rows, so their connections can close
    before returning to the existing generator without changing query logic.
    """

    def __init__(self, path):
        self.path = path

    def __getattr__(self, name):
        if name.startswith("_"):
            raise AttributeError(name)
        def query(*args, **kwargs):
            db = Database(self.path, build_if_missing=False)
            try:
                return getattr(db, name)(*args, **kwargs)
            finally:
                db.close()
        return query

    def close(self):
        pass  # Each query closes its own connection on its originating thread.


def secret_password():
    try:
        return st.secrets.get("admin_password")
    except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
        return None


def admin_authority():
    if "admin_session_id" not in st.session_state:
        st.session_state.admin_session_id = uuid.uuid4().hex
    return AdminAuthority(secret_password, st.session_state.admin_session_id)


def invalidate_workspace():
    old = st.session_state.pop("workspace", None)
    if old is not None:
        old.close()
    for key in ("workspace_signature", "last_feedback", "training_feedback", "model_results",
                "model_n", "last_generated", "run_note", "training_order", "training_review",
                "training_pending", "training_error", "generated",
                "live_feed", "live_stats", "live_rounds", "live_trace", "generated_dirty"):
        st.session_state.pop(key, None)
    st.session_state.live_running = False
    st.session_state.run_running = False


def reset_live(workspace):
    st.session_state.live_running = False
    st.session_state.live_feed = []
    st.session_state.live_stats = {}
    st.session_state.live_rounds = 0
    st.session_state.live_trace = []
    st.session_state.generated = workspace.generated
    st.session_state.generated_dirty = False


def get_workspace(service=None):
    if service is not None:
        service.require_admin()
    names = ("hospital_people.json", "hospital_emails_mixed.json", "history_log.jsonl",
             "generated_emails.json", "practice_sessions.json", "simulation.db")
    signature = (str(PROJECT_ROOT), tuple(
        (name, (PROJECT_ROOT / "data" / name).stat().st_mtime_ns)
        for name in names if (PROJECT_ROOT / "data" / name).exists()))
    workspace = st.session_state.get("workspace")
    if workspace is None or st.session_state.get("workspace_signature") != signature:
        if workspace is not None:
            workspace.close()
        with st.spinner("Loading the latest records…"):
            workspace = service.load_workspace() if service else Workspace(PROJECT_ROOT)
            database = workspace.generator.db
            database.close()
            workspace.generator.db = _SessionDatabase(database.path)
        st.session_state.workspace = workspace
        st.session_state.workspace_signature = signature
    st.session_state.generated = workspace.generated
    if "live_feed" not in st.session_state:
        reset_live(workspace)
    return workspace


@st.fragment(run_every="15s")
def render_report(view, service, person_id):
    """Refresh source-backed tables without resetting navigation or form state."""
    try:
        workspace = get_workspace(service)
        view(service, workspace, person_id)
    except Exception as exc:
        st.error("Could not refresh this view: %s" % exc)

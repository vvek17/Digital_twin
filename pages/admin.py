"""Instructor workspace. Every service call requires backend authorization."""

import streamlit as st

from backend.admin import AdminService
from frontend import responsive, runtime
from frontend.admin_emails import render_emails
from frontend.admin_experiments import render_live, render_model, render_run
from frontend.admin_reports import render_dashboard, render_history, render_person
from frontend.admin_system import render_system
from frontend.layout import page_header, card, main_screens


st.set_page_config(page_title="ALERT - Admin", layout="wide", initial_sidebar_state="auto")
responsive.inject()
with st.sidebar:
    st.header("ALERT")
    main_screens()
authority = runtime.admin_authority()
try:
    authority.require(st.session_state.get("admin_auth_token"))
except PermissionError:
    st.session_state.pop("admin_auth_token", None)
    st.session_state.live_running = False
    with st.container(horizontal_alignment="center"), st.container(width=480), card(key="card_login"):
        st.title("ALERT admin login")
        if not authority.configured:
            st.info("Admin access is locked. Set admin_password in .streamlit/secrets.toml "
                    "or in deployment secrets, then reload this page.")
        with st.form("admin_login"):
            st.text_input("Admin password", type="password", key="admin_password_input")
            submitted = st.form_submit_button("Log in", disabled=not authority.configured)
        if submitted:
            candidate = st.session_state.pop("admin_password_input", "")
            try:
                st.session_state.admin_auth_token = authority.login(candidate)
                st.rerun()
            except PermissionError:
                st.error("Incorrect password.")
    st.stop()

service = AdminService(runtime.PROJECT_ROOT, authority,
                       lambda: st.session_state.get("admin_auth_token"),
                       job_provider=lambda: bool(st.session_state.get("live_running")
                                                 or st.session_state.get("run_running")))
with st.sidebar:
    if st.button("Log out"):
        authority.logout(st.session_state.pop("admin_auth_token", None))
        st.session_state.pop("admin_password_input", None)
        st.session_state.live_running = False
        st.rerun()
    section = st.radio("Admin tools", ["Dashboard", "Live", "Person", "All history",
                                         "Run", "Model", "Emails", "System"], key="admin_section", width="stretch")
    with st.expander("Workspace tools"):
        st.caption("History source: data/history_log.jsonl")
        if st.button("Reload saved history", disabled=bool(st.session_state.get("live_running")
                                                           or st.session_state.get("run_running"))):
            runtime.invalidate_workspace()
            st.rerun()

titles = {"Dashboard": "Workforce overview", "Live": "Live delivery", "Person": "Person report",
          "All history": "Response history", "Run": "Run an experiment", "Model": "Model evaluation",
          "Emails": "Email studio", "System": "System overview"}
page_header(titles[section], "Explore responses and email patterns." if section == "Dashboard" else "")

# Only the selected section executes. System recovery remains available even
# when malformed research data prevents loading the simulation workspace.
if section == "System":
    render_system(service)
else:
    try:
        workspace = runtime.get_workspace(service)
        with st.sidebar:
            person_id = st.selectbox("Staff member", [p.id for p in workspace.people],
                                      format_func=lambda pid: "%s - %s" % (
                                          pid, workspace.people_by_id[pid].name), key="admin_person_id")
            person = workspace.people_by_id[person_id]
            st.caption("%s - %s" % (person.job_title, person.department))
            st.caption("awareness %s · workload %s · %s shift" % (
                person.security_awareness, person.workload, person.shift))
            st.metric("Answers on file", sum(len(workspace.twin.get_history(p.id))
                                               for p in workspace.people))
            if section in ("Live", "Run"):
                st.subheader("How answers are made")
                st.caption("Automatic answers inspect the email. Hidden probabilities are not used.")
                st.toggle("Build new emails", key="build_new", value=True,
                          help="On: build a new dynamic email for each delivery. Off: reuse saved generated emails.")
                st.toggle("Allow repeats", key="allow_repeats", value=True)
        if section != "Live" and st.session_state.get("live_running"):
            st.session_state.live_running = False
            st.info("Live delivery stopped when you left the Live section.")
        views = {"Dashboard": render_dashboard, "Live": render_live,
                 "Person": render_person, "All history": render_history,
                 "Run": render_run, "Model": render_model, "Emails": render_emails}
        if section in ("Dashboard", "Person", "All history", "Emails"):
            runtime.render_report(views[section], service, person_id)
        else:
            views[section](service, workspace, person_id)
    except Exception as exc:
        st.error("%s could not load: %s. System tools remain available in the sidebar." % (section, exc))

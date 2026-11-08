"""ALERT training: answer emails and review human practice results."""

import streamlit as st

from frontend import responsive
from frontend.runtime import get_workspace
from frontend.training_views import render_inbox, render_progress
from frontend.layout import page_header, main_screens


st.set_page_config(page_title="ALERT - App", layout="wide", initial_sidebar_state="auto")
responsive.inject()
# Switching from a running admin simulation to training stops future bursts.
st.session_state.live_running = False
with st.sidebar:
    st.header("ALERT")
    main_screens()

workspace = get_workspace()
with st.sidebar:
    section = st.radio("App tools", ["Inbox", "Training progress"], key="training_view", width="stretch")
    person_id = st.selectbox(
        "Fictional staff member", [p.id for p in workspace.people],
        index=next((i for i, p in enumerate(workspace.people)
                    if p.id == st.session_state.get("admin_person_id")
                    and any(s["person_id"] == p.id for s in workspace.practice_sessions)), 0),
        format_func=lambda pid: "%s - %s" % (pid, workspace.people_by_id[pid].name),
        key="training_person_id")
    person = workspace.people_by_id[person_id]
    st.caption("%s - %s" % (person.job_title, person.department))
    with st.expander("About this workspace"):
        st.caption("Choose a fictional persona to practice. These are not private user accounts.")

page_header(section, "Practice spotting phishing emails and learn from your answers.", area="App")


@st.fragment(run_every="15s")
def training_panel(person_id, view):
    try:
        current = get_workspace()
        view(current, person_id)
    except Exception as exc:
        st.error("Could not refresh training: %s" % exc)


if section == "Inbox":
    training_panel(person_id, render_inbox)
else:
    training_panel(person_id, render_progress)

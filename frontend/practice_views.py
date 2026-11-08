"""Assignment controls inside the existing protected Person report."""

import uuid

import streamlit as st

from backend.practice import MAX_PRACTICE_EMAILS, current_session, session_records
from frontend.layout import card, columns


def render_assignment(service, workspace, person_id):
    service.require_admin()
    person = workspace.people_by_id[person_id]
    session = current_session(workspace, person_id)
    with card("Assign manual practice", key="card_assign_practice"):
        st.caption("Prepare in-app emails for %s to answer using Spam / Not spam in App → Inbox. "
                   "This does not send real email or generate simulated answers." % person.name)
        notice = st.session_state.pop("practice_notice", None)
        if notice:
            st.success(notice)
        if session:
            answered = len({record["email_id"] for record in session_records(workspace, session)})
            st.progress(answered / session["count"], text="%d of %d assigned emails answered" % (
                answered, session["count"]))
            if answered < session["count"]:
                st.info("Practice is ready for %s. Select this person in App → Inbox to continue. "
                        "Complete this session before assigning another." % person.name)
                return
            st.caption("The previous session is complete. Existing answers and scores are retained.")
        previous_id = session["id"] if session else "first"
        request_key = "practice_request_%s_%s" % (person_id, previous_id)
        request_id = st.session_state.setdefault(request_key, uuid.uuid4().hex)
        with st.form("assign_practice_%s_%s" % (person_id, previous_id)):
            field, action = columns(key="practice_setup", kind="controls", vertical_alignment="bottom")
            with field:
                count = st.number_input("Practice emails", min_value=1, max_value=MAX_PRACTICE_EMAILS,
                                        value=5, step=1, key="practice_count_%s_%s" % (person_id, previous_id),
                                        help="Whole numbers from 1 to 1,000,000, matching the existing Run limit.")
            with action:
                assign = st.form_submit_button("Assign practice", type="primary")
            st.caption("Reuse available generated emails first. Build only the remainder using the existing "
                       "email generator. The full requested count must be ready before anything is assigned.")
        if assign:
            progress = st.progress(0.0, text="Preparing practice emails…")
            try:
                result = service.assign_practice(
                    workspace, person_id, count, request_id,
                    on_progress=lambda done, total: progress.progress(
                        done / total, text="Prepared %d of %d emails" % (done, total)))
                st.session_state.practice_notice = (
                    "Assigned %d practice emails to %s. Open App → Inbox and select this person."
                    % (result["count"], person.name))
                st.rerun()
            except Exception as exc:
                st.error("Could not assign practice: %s" % exc)
            finally:
                progress.empty()

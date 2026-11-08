"""The trainee's inbox, explanations, and human-answer progress."""

import random

import pandas as pd
import streamlit as st

from backend.training import submit_answer, training_records, unanswered_emails
from frontend.tables import show_table
from frontend.layout import card, columns
from frontend.email_presentation import email_markup, feedback_markup
from backend.practice import current_session, practice_emails, session_records


def render_training_stats(records, key):
    correct = sum(bool(r["correct"]) for r in records)
    a, b, c = columns(3, key=key, kind="metrics")
    a.metric("Answered", len(records))
    b.metric("Correct", correct)
    c.metric("Accuracy", "%.0f%%" % (100 * correct / len(records)))


def render_feedback(feedback, record=None, email=None, records=None):
    st.subheader("Answer review")
    if not feedback and record is None:
        st.caption("Choose Spam or Not spam. Your result and explanation will appear here.")
        return
    st.html(feedback_markup(feedback, record, email))
    if records:
        st.markdown("**Your practice progress**")
        render_training_stats(records, "inbox_progress")


def _queue_answer(person_id, email_id, said_spam):
    """Capture the displayed email's identity before the submission rerun."""
    if st.session_state.get("training_pending"):
        return
    if st.session_state.get("training_review", {}).get(person_id) == email_id:
        return
    st.session_state.training_pending = {
        "person_id": person_id, "email_id": email_id, "said_spam": said_spam}


def render_inbox(workspace, person_id):
    person = workspace.people_by_id[person_id]
    session = current_session(workspace, person_id)
    pool = practice_emails(workspace, person_id)
    if not pool:
        st.info("No generated practice emails are available yet. Ask an administrator to assign "
                "practice in Admin → Person or generate emails in Admin → Emails.")
        return
    order = st.session_state.get("training_order")
    if order is None or set(order) != {e["id"] for e in pool}:
        order = [e["id"] for e in pool]
        random.shuffle(order)
        st.session_state.training_order = order
    rank = {identity: pos for pos, identity in enumerate(order)}
    queue = sorted(unanswered_emails(workspace, person_id), key=lambda e: rank[e["id"]])
    records = session_records(workspace, session) if session else training_records(workspace, person_id)
    review_id = st.session_state.get("training_review", {}).get(person_id)
    record = next((r for r in reversed(records) if r["email_id"] == review_id), None)
    email = next((e for e in pool if record is not None and e["id"] == review_id), None)
    reviewing = email is not None
    if not reviewing:
        st.session_state.get("training_review", {}).pop(person_id, None)
        if not queue:
            st.success("%s has completed all %d practice emails. Review Training progress or choose "
                       "another fictional persona." % (person.name, len(pool)))
            if records:
                render_training_stats(records, "completed_progress")
            return
        email = queue[0]
    pending = st.session_state.get("training_pending")
    # A queued click belongs only to the message that was displayed. A stale
    # event must never answer the next message or a different person's email.
    if pending and (reviewing or pending["person_id"] != person_id
                    or pending["email_id"] != email["id"]):
        st.session_state.pop("training_pending", None)
        pending = None
    if session:
        st.caption("Assigned practice · %d emails for %s" % (session["count"], person.name))
    st.caption("%d of %d emails left for %s" % (len(queue), len(pool), person.name))
    error = st.session_state.pop("training_error", None)
    if error:
        st.error(error)
    left, right = columns(key="training_inbox")
    with left, card(key="card_training_email"):
        st.caption("Reviewed email" if reviewing else "Incoming email")
        st.html(email_markup(email))
        if reviewing:
            st.caption("Your answer has been recorded. Read the feedback before continuing.")
        else:
            st.markdown("**Is this spam?**")
            b1, b2 = columns(key="training_answers", kind="actions")
            b1.button("Spam", type="primary", width="stretch", disabled=bool(pending),
                      key="training_spam_%s_%s" % (person_id, email["id"]),
                      help="Flag this email as spam or phishing.",
                      on_click=_queue_answer, args=(person_id, email["id"], True))
            b2.button("Not spam", width="stretch", disabled=bool(pending),
                      key="training_safe_%s_%s" % (person_id, email["id"]),
                      help="Treat this email as genuine.",
                      on_click=_queue_answer, args=(person_id, email["id"], False))
    with right, card(key="card_training_feedback"):
        feedback = st.session_state.get("training_feedback", {}).get(person_id) if reviewing else None
        render_feedback(feedback, record if reviewing else None,
                        email if reviewing else None, records if reviewing else None)
        if reviewing:
            if queue and st.button("Next email", type="primary", key="training_next_%s" % person_id):
                st.session_state.get("training_review", {}).pop(person_id, None)
                st.session_state.get("training_feedback", {}).pop(person_id, None)
                st.rerun()
            elif not queue:
                st.success("All practice emails completed. You can review your results in Training progress.")
    if pending:
        try:
            with st.spinner("Saving your answer…"):
                result = submit_answer(workspace, person_id, email["id"], pending["said_spam"])
            st.session_state.setdefault("training_feedback", {})[person_id] = result
            st.session_state.setdefault("training_review", {})[person_id] = email["id"]
        except Exception as exc:
            st.session_state.training_error = "Could not record the answer: %s" % exc
        finally:
            st.session_state.pop("training_pending", None)
        st.rerun()


def render_progress(workspace, person_id):
    st.caption("Practice results for %s" % workspace.people_by_id[person_id].name)
    st.caption("Human Inbox answers for this fictional persona. Simulated responses are excluded.")
    records = training_records(workspace, person_id)
    if not records:
        st.info("No practice answers yet. Start in Inbox.")
        return
    render_training_stats(records, "training_progress")
    choice = st.radio("Show answers", ["All", "Only wrong", "Only correct"], horizontal=True)
    shown = [r for r in reversed(records) if choice == "All"
             or bool(r["correct"]) == (choice == "Only correct")]
    history, review = columns(key="training_review")
    with history, card("Your answers", key="card_training_answers"):
        show_table(pd.DataFrame([{"email": str(r["email_id"]), "subject": r["subject"],
                                  "really was": r["truth"], "they said": r["said"],
                                  "result": "correct" if r["correct"] else "incorrect"} for r in shown]),
                   visible=["result", "they said", "subject"])
        st.caption("Use the table's columns menu to show the email ID and correct classification.")
    with review, card("Review an email", key="card_training_review"):
        identities = list(dict.fromkeys(r["email_id"] for r in reversed(records)))
        by_id = {e["id"]: e for e in workspace.emails + workspace.generated}
        selected = st.selectbox("Review an answered email", identities,
                                format_func=lambda i: "%s — %s" % (i, by_id.get(i, {}).get("subject", "Unavailable")))
        email = by_id.get(selected)
        if email:
            answer = next(r for r in reversed(records) if r["email_id"] == selected)
            st.caption("You said %s · Actually %s" % (answer["said"], answer["truth"]))
            st.html(email_markup(email))
            for note in email.get("red_flags") or email.get("safe_signs") or []:
                st.markdown("- %s" % note)

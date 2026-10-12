# app.py
# A simple web interface (Streamlit) for the phishing twin.
#
# A real person reads one email at a time and clicks:
#   "Clicked it (Yes)"  -> recorded as action "click"
#   "Did not click (No)" -> recorded as action "ignore"
# After every answer the twin updates its counters and its live guesses
# are shown as a bar chart. It keeps going, email after email.
#
# Run it with:   streamlit run app.py

import json
import os
import random
from datetime import datetime

import pandas as pd
import streamlit as st

from persona import load_people
from generator import EmailGenerator
from twin import TwinPredictor

CUES = ["urgency", "authority", "it_login", "hr_payroll", "billing", "false_report"]

# Every Yes/No answer is appended here as one record (a growing JSON list).
RESPONSES_PATH = os.path.join("data", "responses.json")


def load_responses():
    """Read all saved answers (returns an empty list if the file is missing/empty)."""
    try:
        with open(RESPONSES_PATH) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_response(record):
    """Append one answer to the JSON file."""
    responses = load_responses()
    responses.append(record)
    os.makedirs("data", exist_ok=True)
    with open(RESPONSES_PATH, "w") as f:
        json.dump(responses, f, indent=2)


# ---- load data once (cached so it does not reload on every click) ----
@st.cache_data
def get_people():
    return load_people()


@st.cache_data
def get_emails():
    return EmailGenerator().emails


people = get_people()
emails = get_emails()
people_by_id = {p.id: p for p in people}


# ---- set up memory that survives button clicks ----
def reset_session():
    st.session_state.twin = TwinPredictor()
    order = list(range(len(emails)))
    random.shuffle(order)
    st.session_state.order = order
    st.session_state.pos = 0
    st.session_state.count = 0
    st.session_state.last = None


if "twin" not in st.session_state:
    reset_session()


# ---- page layout ----
st.set_page_config(page_title="Phishing Twin Trainer", layout="wide")
st.title("Phishing Twin Trainer")
st.caption("Read each email, decide if this person would click it, and watch the twin learn.")

# Sidebar: pick which staff member we are answering for, and a reset button.
with st.sidebar:
    st.header("Settings")
    person_id = st.selectbox(
        "Staff member",
        options=[p.id for p in people],
        format_func=lambda pid: "%s - %s (%s)" % (pid, people_by_id[pid].name, people_by_id[pid].role),
    )
    st.write("Emails answered this session: **%d**" % st.session_state.count)
    if st.button("Reset twin", use_container_width=True):
        reset_session()
        st.rerun()

    st.divider()
    saved = load_responses()
    st.write("Saved to `data/responses.json`: **%d** answers" % len(saved))
    if saved:
        st.download_button(
            "Download responses.json",
            data=json.dumps(saved, indent=2),
            file_name="responses.json",
            mime="application/json",
            use_container_width=True,
        )

twin = st.session_state.twin

# The email the person is looking at right now.
order = st.session_state.order
current_index = order[st.session_state.pos % len(order)]
email = emails[current_index]

# ---- two columns: email on the left, twin's live guesses on the right ----
left, right = st.columns([3, 2])

with left:
    st.subheader("Incoming email")
    st.markdown(
        "**From:** %s  \n**Subject:** %s"
        % (email.get("sender_name", "Unknown"), email["subject"])
    )
    st.text_area("Message", email["body"], height=240, disabled=True, label_visibility="collapsed")

    st.write("Would this person click it?")
    c1, c2 = st.columns(2)
    clicked_yes = c1.button("Clicked it (Yes)", type="primary", use_container_width=True)
    clicked_no = c2.button("Did not click (No)", use_container_width=True)

    if clicked_yes or clicked_no:
        action = "click" if clicked_yes else "ignore"
        twin.update(person_id, email, action)
        st.session_state.count += 1
        st.session_state.last = {
            "subject": email["subject"],
            "label": email["label"],
            "cue": email["cue"],
            "action": action,
        }
        # Save this answer to data/responses.json so it persists.
        save_response({
            "time": datetime.now().isoformat(timespec="seconds"),
            "person_id": person_id,
            "person_name": people_by_id[person_id].name,
            "email_id": email["id"],
            "cue": email["cue"],
            "label": email["label"],
            "answer": "yes" if clicked_yes else "no",
            "action": action,
        })
        st.session_state.pos += 1
        st.rerun()

    # Show what the previous email really was, after it was answered.
    last = st.session_state.last
    if last:
        kind = "phishing" if last["label"] == "phishing" else "legitimate (safe)"
        st.info(
            "Last email was **%s** (cue: %s). You answered **%s**."
            % (kind, last["cue"], "Yes" if last["action"] == "click" else "No")
        )

with right:
    st.subheader("Twin's current guesses")
    estimates = twin.get_all_estimates(person_id)
    df = pd.DataFrame(
        {"twin guess": [round(estimates[c], 3) for c in CUES]},
        index=CUES,
    )
    st.bar_chart(df, y="twin guess")
    st.caption("Each bar is the twin's guessed chance (0 to 1) for that cue, learned only from your Yes/No answers.")
    st.dataframe(df, use_container_width=True)

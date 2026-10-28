# app.py
# The front desk for the phishing digital twin.
#
# Four views:
#   Dashboard  - the whole workforce at a glance: who clicks, who knows
#   Inbox      - answer emails one at a time and get feedback
#   Person     - drill into one person's counters and history
#   Run        - drive the simulation automatically
#
# The model behind it all, from the project diagram:
#     P(click) = yes / (yes + no)     yes = clicked, no = reported
# Everything starts at 0 and moves only on answers.
#
# Run it with:   streamlit run app.py

import os
import random
import time
from datetime import datetime

import altair as alt
import pandas as pd
import streamlit as st

from persona import load_people
from generator import EmailGenerator
from twin import TwinPredictor, HISTORY_PATH
from feedback import FeedbackModule
from human import SimulatedHuman
from reader import RuleReader
from email_builder import EmailBuilder, RECIPES as GEN_RECIPES
import modifications as MODS
from email_generator import EmailGeneratorLLM, OUT_CSV as GEN_CSV

# The backend. Nothing below this line opens a file, runs a delivery or
# computes a rate - it asks one of these and draws the answer.
import benchmark
import store
from engine import DeliveryEngine
from metrics import CUES, workforce_frame
from theme import (AWARENESS_SCALE, CLICKED, GRID, INK, MUTED, RECOGNISED,
                   verdict_of)

@st.cache_data
def get_people():
    return load_people()


@st.cache_data
def get_emails():
    return EmailGenerator().emails


people = get_people()
emails = get_emails()
people_by_id = {p.id: p for p in people}


def reset_session(keep_history=True):
    # The log is the source of truth, so a reload replays it rather than
    # trusting the snapshot.
    st.session_state.twin = (TwinPredictor.from_log() if keep_history
                             else TwinPredictor())
    # Needed so the CSV rows carry the person's name, role and traits.
    st.session_state.twin.people_by_id = people_by_id
    st.session_state.feedback_module = FeedbackModule("detailed")
    order = list(range(len(emails)))
    random.shuffle(order)
    st.session_state.order = order
    st.session_state.pos = 0
    st.session_state.count = 0
    st.session_state.last_feedback = None
    st.session_state.auto_results = None
    reset_live()


def reset_live():
    """Clear the live feed and its session tallies."""
    st.session_state.live_running = False
    st.session_state.live_feed = []
    st.session_state.live_stats = {}
    st.session_state.live_rounds = 0
    st.session_state.live_trace = []
    st.session_state.generated = store.load_generated()
    st.session_state.generated_dirty = False


if "twin" not in st.session_state:
    reset_session()
if "live_running" not in st.session_state:
    reset_live()

twin = st.session_state.twin


@st.cache_resource
def get_builder():
    """One builder, reused - it holds the genuine emails it starts from."""
    return EmailBuilder()


@st.cache_resource
def get_readers():
    """One rule reader per person - decides by inspecting the email."""
    return {p.id: RuleReader(p) for p in load_people()}


@st.cache_resource
def get_humans():
    """One dice-roller per person - decides from hidden_probs."""
    return {p.id: SimulatedHuman(p) for p in load_people()}


def answerer_for(person_id):
    """Whichever answering model is currently selected."""
    if st.session_state.get("use_reader", True):
        return get_readers()[person_id]
    return get_humans()[person_id]


def get_engine():
    """The delivery engine, pointed at whatever the sidebar currently says.

    Rebuilt per call rather than cached: the toggles decide who answers and
    how the email is chosen, and a cached engine would keep the old answer.
    """
    return DeliveryEngine(
        twin=twin, people=people, emails=emails,
        answerer_for=answerer_for, generator=EmailGenerator(),
        builder=get_builder(), feedback=st.session_state.feedback_module,
    )


def live_step():
    """One delivery, plus the session-only tallies the boards read."""
    generated = st.session_state.generated
    before = len(generated)

    rec = get_engine().deliver(
        build_new=st.session_state.get("build_new", True),
        allow_repeats=st.session_state.get("allow_repeats", True),
        generated=generated,
    )
    if rec is None:
        return None
    if len(generated) > before:
        st.session_state.generated_dirty = True

    # Session-only tallies, so the boards show THIS run rather than all history.
    tally = st.session_state.live_stats.setdefault(
        rec["person_id"], {"name": rec["person"], "awareness": rec["awareness"],
                           "seen": 0, "clicked": 0, "reported": 0})
    if rec["label"] == "phishing":
        tally["seen"] += 1
        if rec["action"] == "click":
            tally["clicked"] += 1
        elif rec["action"] == "report":
            tally["reported"] += 1

    st.session_state.live_rounds += 1

    # A running trace of P(click) per cue, so the movement can be plotted.
    if rec["label"] == "phishing":
        st.session_state.live_trace.append({
            "round": st.session_state.live_rounds,
            "cue": rec["cue"],
            "p_click": rec["p_after"],
        })
        del st.session_state.live_trace[:-600]

    return rec


# ------------------------------------------------------------------ sidebar

st.set_page_config(page_title="Phishing Twin - Front Desk", layout="wide")

with st.sidebar:
    st.header("Front desk")
    person_id = st.selectbox(
        "Staff member",
        options=[p.id for p in people],
        format_func=lambda pid: "%s - %s" % (pid, people_by_id[pid].name),
    )
    person = people_by_id[person_id]
    st.caption("%s - %s" % (person.job_title, person.department))
    st.caption("awareness %s · workload %s · %s shift"
               % (person.security_awareness, person.workload, person.shift))

    st.divider()
    on_file = sum(len(twin.get_history(p.id)) for p in people)
    st.metric("Answers on file", "%d" % on_file)
    st.caption("`%s`" % HISTORY_PATH)

    st.divider()
    st.subheader("How answers are made")
    st.toggle(
        "Read the email",
        key="use_reader", value=True,
        help=("On: the answer comes from inspecting the email - sender domain, "
              "Reply-To, link, wording. No invented numbers.\n\n"
              "Off: the old model - a dice roll against each person's secret "
              "hidden_probs. The email is never read."),
    )
    st.toggle(
        "Build new emails",
        key="build_new", value=True,
        help=("On: every delivery assembles a brand new email from a genuine "
              "one plus modifications, so nothing repeats.\n\n"
              "Off: draw from the fixed set of 51."),
    )
    st.toggle(
        "Allow repeats",
        key="allow_repeats", value=True,
        help=("On: an email can arrive again at a different moment, so volume "
              "builds up.\n\nOff: each person sees each email once - 51 max."),
    )
    st.caption(
        "Reading the email" if st.session_state.get("use_reader", True)
        else ":red[Using hidden_probs - invented numbers]"
    )
    if st.session_state.get("build_new", True):
        st.caption("Built on the fly: **%d** emails so far"
                   % len(st.session_state.generated))

    if st.button("Reload saved history", width='stretch'):
        reset_session(keep_history=True)
        st.rerun()


st.title("Phishing Digital Twin")
st.caption("P(click) = yes / (yes + no)  ·  yes = clicked, no = reported  ·  everything starts at 0")

tab_dash, tab_live, tab_inbox, tab_person, tab_history, tab_run, tab_model, tab_emails = st.tabs(
    ["Dashboard", "Live", "Inbox", "Person", "All history", "Run", "Model", "Emails"]
)


# ==================================================================== DASHBOARD

with tab_dash:
    wf = workforce_frame(twin, people)
    seen_total = int(wf["seen"].sum())

    if seen_total == 0:
        st.info(
            "No history yet. Open the **Run** tab to let the simulation build one, "
            "or answer emails yourself in **Inbox**."
        )
    else:
        clicked_total = int(wf["clicked"].sum())
        reported_total = int(wf["reported"].sum())

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Phishing delivered", "%d" % seen_total)
        c2.metric("Clicked", "%.0f%%" % (100 * clicked_total / seen_total))
        c3.metric("Recognised", "%.0f%%" % (100 * reported_total / seen_total))
        c4.metric("Staff tracked", "%d" % int((wf["seen"] > 0).sum()))

        st.divider()

        left, right = st.columns([3, 2])

        with left:
            st.subheader("Who clicks")
            st.caption("Share of phishing emails clicked, by person. Colour is their security awareness.")

            ranked = wf[wf["seen"] > 0].sort_values("click_rate", ascending=False)
            bars = (
                alt.Chart(ranked)
                .mark_bar(cornerRadiusEnd=4, height=14)
                .encode(
                    x=alt.X("click_rate:Q", title="clicked",
                            axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 1])),
                    y=alt.Y("name:N", sort="-x", title=None),
                    color=alt.Color(
                        "awareness:N",
                        title="awareness",
                        scale=alt.Scale(domain=list(AWARENESS_SCALE),
                                        range=list(AWARENESS_SCALE.values())),
                        legend=alt.Legend(orient="top"),
                    ),
                    tooltip=[
                        alt.Tooltip("name:N", title="person"),
                        alt.Tooltip("role:N", title="role"),
                        alt.Tooltip("awareness:N"),
                        alt.Tooltip("seen:Q", title="phishing seen"),
                        alt.Tooltip("clicked:Q"),
                        alt.Tooltip("click_rate:Q", title="click rate", format=".0%"),
                    ],
                )
                .properties(height=max(260, 20 * len(ranked)))
            )
            st.altair_chart(
                bars.configure_view(strokeWidth=0).configure_axis(
                    labelColor=MUTED, titleColor=MUTED, domainColor=GRID,
                    tickColor=GRID, gridColor=GRID,
                ).configure_legend(labelColor=MUTED, titleColor=MUTED),
                width='stretch',
            )

        with right:
            st.subheader("Clicked vs recognised")
            st.caption("By awareness level. The two bars answer the same question from opposite sides.")

            by_aware = (
                wf[wf["seen"] > 0]
                .groupby("awareness", as_index=False)[["seen", "clicked", "reported"]]
                .sum()
            )
            by_aware["clicked rate"] = by_aware["clicked"] / by_aware["seen"]
            by_aware["recognised rate"] = by_aware["reported"] / by_aware["seen"]
            melted = by_aware.melt(
                id_vars=["awareness", "seen"],
                value_vars=["clicked rate", "recognised rate"],
                var_name="outcome", value_name="rate",
            )
            melted["outcome"] = melted["outcome"].str.replace(" rate", "", regex=False)

            grouped = (
                alt.Chart(melted)
                .mark_bar(cornerRadiusEnd=4)
                .encode(
                    x=alt.X("outcome:N", title=None, axis=alt.Axis(labelAngle=0)),
                    y=alt.Y("rate:Q", title="share of phishing",
                            axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 1])),
                    color=alt.Color(
                        "outcome:N", title=None,
                        scale=alt.Scale(domain=["clicked", "recognised"],
                                        range=[CLICKED, RECOGNISED]),
                        legend=alt.Legend(orient="top"),
                    ),
                    column=alt.Column("awareness:N", title=None,
                                      sort=["low", "medium", "high"],
                                      header=alt.Header(labelColor=MUTED)),
                    tooltip=[
                        alt.Tooltip("awareness:N"),
                        alt.Tooltip("outcome:N"),
                        alt.Tooltip("rate:Q", format=".0%"),
                        alt.Tooltip("seen:Q", title="phishing seen"),
                    ],
                )
                .properties(width=90, height=300)
            )
            st.altair_chart(grouped, width='content')

        st.divider()
        st.subheader("What works on people")

        # Every field on an email that can group it. The first four describe
        # the attack, the last four come from the course table.
        BREAKDOWNS = {
            "Cue": "cue",
            "Technique": "technique",
            "Address trick": "address_trick",
            "Difficulty": "difficulty",
            "CIA hit": "cia_hit",
            "Week": "week",
            "Category": "technique_category",
            "Target role": "target_role",
        }
        dim = st.radio("Break down by", list(BREAKDOWNS), horizontal=True)
        field = BREAKDOWNS[dim]

        st.caption(
            "Share of those phishing emails that people trusted. "
            "Higher means it works better on them."
        )

        # Join each answer back to the email it came from, so any field on the
        # email can be the breakdown - not just the cue stored in the history.
        email_by_id = {e["id"]: e for e in emails}
        email_by_id.update({e["id"]: e for e in st.session_state.generated})
        rows = []
        for p in people:
            for ev in twin.get_history(p.id):
                if ev["label"] != "phishing" or "correct" not in ev:
                    continue
                src_email = email_by_id.get(ev["email_id"])
                if not src_email:
                    continue
                rows.append({
                    "type": src_email.get(field, "-"),
                    "fooled": not ev["correct"],
                })

        if not rows:
            st.caption("No phishing answers yet.")
        else:
            bdf = pd.DataFrame(rows)
            agg = bdf.groupby("type").agg(
                asked=("fooled", "size"),
                fooled=("fooled", "sum"),
            ).reset_index()
            agg["rate"] = agg["fooled"] / agg["asked"]
            agg = agg.sort_values("rate", ascending=False)

            bars = (
                alt.Chart(agg)
                .mark_bar(cornerRadiusEnd=4, height=20, color=CLICKED)
                .encode(
                    x=alt.X("rate:Q", title="trusted the spam",
                            axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 1])),
                    y=alt.Y("type:N", sort="-x", title=None),
                    tooltip=[
                        alt.Tooltip("type:N", title=dim),
                        alt.Tooltip("asked:Q", title="times asked"),
                        alt.Tooltip("fooled:Q", title="trusted it"),
                        alt.Tooltip("rate:Q", title="rate", format=".0%"),
                    ],
                )
                .properties(height=max(150, 26 * len(agg)))
            )
            blabels = bars.mark_text(align="left", dx=6, color=INK, fontSize=11).encode(
                text=alt.Text("rate:Q", format=".0%"))

            st.altair_chart(
                (bars + blabels).configure_view(strokeWidth=0).configure_axis(
                    labelColor=MUTED, titleColor=MUTED, domainColor=GRID,
                    tickColor=GRID, gridColor=GRID,
                ),
                width='stretch',
            )

            with st.expander("%s table" % dim):
                out = agg.rename(columns={"type": dim.lower(),
                                          "fooled": "trusted it"}).copy()
                out["rate"] = (100 * out["rate"]).round(0).astype(int).astype(str) + "%"
                st.dataframe(out, width='stretch', hide_index=True)

        # ---- per-person scoreboard: judged, correct, wrong ----
        scores = []
        for p in people:
            sc = twin.get_score(p.id)
            if sc["answered"]:
                scores.append({
                    "id": p.id, "name": p.name, "awareness": p.security_awareness,
                    "judged": sc["answered"], "correct": sc["correct"],
                    "incorrect": sc["wrong"],
                    "accuracy": round(100 * sc["accuracy"]),
                    "spam trusted": sc["missed_spam"],
                    "genuine flagged": sc["false_alarms"],
                })
        if scores:
            st.divider()
            st.subheader("Spam judgements per person")
            st.caption(
                "How many each person judged, and how many they got right. "
                "The last two columns split the mistakes: spam they trusted "
                "versus genuine mail they flagged."
            )
            sdf = pd.DataFrame(scores).sort_values("accuracy", ascending=False)
            st.dataframe(
                sdf.assign(accuracy=sdf["accuracy"].astype(str) + "%"),
                width='stretch', hide_index=True,
            )

        with st.expander("Table view"):
            show = wf[wf["seen"] > 0].copy()
            show["click_rate"] = (100 * show["click_rate"]).round(0).astype(int).astype(str) + "%"
            show["report_rate"] = (100 * show["report_rate"]).round(0).astype(int).astype(str) + "%"
            st.dataframe(
                show[["id", "name", "role", "awareness", "seen", "clicked",
                      "reported", "click_rate", "report_rate"]],
                width='stretch', hide_index=True,
            )


# ======================================================================== LIVE

with tab_live:
    st.subheader("Live delivery")
    st.caption(
        "Emails arrive one at a time to random staff. Each line is one delivery "
        "and what that person did with it."
    )

    lc1, lc2, lc3, lc4 = st.columns([1, 1, 1, 2])
    with lc1:
        start = st.button("Start", type="primary", width='stretch',
                          disabled=st.session_state.live_running)
    with lc2:
        stop = st.button("Stop", width='stretch',
                         disabled=not st.session_state.live_running)
    with lc3:
        clear = st.button("Clear", width='stretch')
    with lc4:
        delay = st.select_slider("Speed (seconds per email)",
                                 options=[0.0, 0.1, 0.25, 0.5, 1.0], value=0.25)

    if start:
        st.session_state.live_running = True
    if stop:
        st.session_state.live_running = False
        twin.save(people_by_id=people_by_id)
    if clear:
        reset_live()
        st.rerun()

    status = st.empty()
    latest_box = st.empty()
    trace_box = st.empty()
    feed_box = st.empty()
    boards_box = st.empty()

    def render_live():
        feed = st.session_state.live_feed
        stats = st.session_state.live_stats

        with status.container():
            m1, m2, m3, m4 = st.columns(4)
            seen = sum(s["seen"] for s in stats.values())
            clicked = sum(s["clicked"] for s in stats.values())
            reported = sum(s["reported"] for s in stats.values())
            m1.metric("Delivered", st.session_state.live_rounds)
            m2.metric("Phishing", seen)
            m3.metric("Clicked", "%.0f%%" % (100 * clicked / seen) if seen else "-")
            m4.metric("Recognised", "%.0f%%" % (100 * reported / seen) if seen else "-")

        # ---- the email that just landed, exactly as that person saw it ----
        with latest_box.container():
            if feed:
                rec = feed[0]
                e = rec["email"]
                label, colour = verdict_of(rec)
                st.divider()
                head, side = st.columns([3, 2])

                with head:
                    st.markdown("**Just delivered to %s**  ·  :%s[**%s**]"
                                % (rec["person"], colour, label))
                    st.markdown("**From:** %s `<%s>`"
                                % (e.get("sender_name", "?"), e["sender_email"]))
                    if e.get("reply_to"):
                        st.markdown("**Reply-To:** `%s`" % e["reply_to"])
                    st.markdown("**Subject:** %s" % e["subject"])
                    st.text_area("Body", e["body"], height=160,
                                 disabled=True, label_visibility="collapsed",
                                 key="live_body_%d" % st.session_state.live_rounds)

                with side:
                    if rec["label"] == "phishing":
                        st.markdown("**Counter for `%s`**" % rec["cue"])
                        t1, t2, t3 = st.columns(3)
                        t1.metric("yes", rec["yes"])
                        t2.metric("no", rec["no"])
                        t3.metric("all", rec["all"])
                        st.metric(
                            "P(click) = yes / all",
                            "%.2f" % rec["p_after"],
                            delta="%+.2f" % (rec["p_after"] - rec["p_before"]),
                            delta_color="inverse",
                        )
                        st.caption("was %.2f before this email" % rec["p_before"])
                        if e.get("link_target"):
                            st.caption("Link read `%s`, went to `%s`"
                                       % (e.get("link_text", "?"), e["link_target"]))
                    else:
                        st.info("Legitimate email - no cue, nothing to click.")

        # ---- how P(click) is moving, cue by cue ----
        with trace_box.container():
            trace = st.session_state.live_trace
            if len(trace) > 4:
                st.markdown("**P(click) as it moves**")
                tdf = pd.DataFrame(trace)
                line = (
                    alt.Chart(tdf)
                    .mark_line(strokeWidth=2, interpolate="step-after")
                    .encode(
                        x=alt.X("round:Q", title="email delivered"),
                        y=alt.Y("p_click:Q", title="P(click)",
                                scale=alt.Scale(domain=[0, 1]),
                                axis=alt.Axis(format=".1f")),
                        color=alt.Color("cue:N", title="cue",
                                        scale=alt.Scale(scheme="tableau10"),
                                        legend=alt.Legend(orient="top")),
                        tooltip=["cue", "round",
                                 alt.Tooltip("p_click:Q", format=".2f")],
                    )
                    .properties(height=200)
                )
                st.altair_chart(
                    line.configure_view(strokeWidth=0).configure_axis(
                        labelColor=MUTED, titleColor=MUTED, domainColor=GRID,
                        tickColor=GRID, gridColor=GRID,
                    ).configure_legend(labelColor=MUTED, titleColor=MUTED),
                    width='stretch',
                )
                st.caption("One line per cue, for whichever person each email landed on.")

        with feed_box.container():
            st.markdown("**Arriving now**")
            if not feed:
                st.caption("Press Start.")
            for rec in feed:
                label, colour = verdict_of(rec)
                move = ""
                if rec["label"] == "phishing":
                    move = "  ·  P %.2f → **%.2f**" % (rec["p_before"], rec["p_after"])
                st.markdown(
                    "`%s`  **%s**  ·  %s  ·  `%s`  →  :%s[**%s**]%s"
                    % (rec["time"], rec["person"], rec["cue"],
                       rec["email_id"], colour, label, move)
                )
                if rec["feedback"] and rec["feedback"].get("history_note"):
                    st.caption(rec["feedback"]["history_note"])

        with boards_box.container():
            ranked = [s for s in stats.values() if s["seen"] >= 3]
            if ranked:
                st.divider()
                b1, b2 = st.columns(2)
                with b1:
                    st.markdown(":red[**Who clicks**]")
                    top = sorted(ranked, key=lambda s: -s["clicked"] / s["seen"])[:8]
                    st.dataframe(
                        pd.DataFrame([{
                            "person": s["name"], "awareness": s["awareness"],
                            "seen": s["seen"],
                            "clicked": "%.0f%%" % (100 * s["clicked"] / s["seen"]),
                        } for s in top]),
                        width='stretch', hide_index=True,
                    )
                with b2:
                    st.markdown(":blue[**Who knows**]")
                    top = sorted(ranked, key=lambda s: -s["reported"] / s["seen"])[:8]
                    st.dataframe(
                        pd.DataFrame([{
                            "person": s["name"], "awareness": s["awareness"],
                            "seen": s["seen"],
                            "recognised": "%.0f%%" % (100 * s["reported"] / s["seen"]),
                        } for s in top]),
                        width='stretch', hide_index=True,
                    )

    render_live()

    # Run a short burst, then rerun so the Stop button can register. Streamlit
    # is single-threaded: a long blocking loop would ignore every click.
    if st.session_state.live_running:
        BURST = 12
        for _ in range(BURST):
            rec = live_step()
            if rec is None:
                st.session_state.live_running = False
                st.warning("Everyone has judged every email - nothing left to ask.")
                break
            st.session_state.live_feed.insert(0, rec)
            del st.session_state.live_feed[10:]
            render_live()
            if delay:
                time.sleep(delay)
        twin.save(people_by_id=people_by_id)
        if st.session_state.get("generated_dirty"):
            store.save_generated(st.session_state.generated)
            st.session_state.generated_dirty = False
        st.rerun()


# ======================================================================= INBOX

with tab_inbox:
    # Show only emails this person has not judged yet, in the shuffled order.
    seen_ids = {r["email_id"] for r in twin.get_history(person_id)}
    queue = [emails[i] for i in st.session_state.order
             if emails[i]["id"] not in seen_ids]

    # NB: never call st.stop() here - it halts the whole script, so every tab
    # rendered after this one would silently disappear. Guard with an if.
    if not queue:
        st.success(
            "%s has judged all %d emails. Pick another person in the sidebar, "
            "or see their result in the **Person** tab."
            % (person.name, len(emails))
        )
        email = None
    else:
        email = queue[0]
        st.caption("%d of %d emails left for %s"
                   % (len(queue), len(emails), person.name))

    left, right = st.columns([3, 2]) if email else (st.container(), st.container())

    with left:
      if email:
        st.subheader("Incoming email")
        st.markdown("**From:** %s `<%s>`" % (email.get("sender_name", "Unknown"),
                                             email["sender_email"]))
        st.markdown("**Subject:** %s" % email["subject"])
        st.text_area("Message", email["body"], height=240,
                     disabled=True, label_visibility="collapsed")

        st.write("Is this spam?")
        b1, b2 = st.columns(2)
        said_spam = b1.button("Spam", type="primary", width='stretch')
        said_safe = b2.button("Not spam", width='stretch')

        if said_spam or said_safe:
            # "Spam" means they flagged it, whatever it really was.
            # "Not spam" means they trusted it - on a phishing email, that is
            # the click; on a genuine one, it is the correct non-action.
            if said_spam:
                action = "report"
            else:
                action = "click" if email["label"] == "phishing" else "ignore"
            twin.update(person_id, email, action, source="app")
            twin.save(people_by_id=people_by_id)

            key = "false_report" if email["label"] == "legitimate" else email["cue"]
            st.session_state.last_feedback = st.session_state.feedback_module.give_feedback(
                email, action, twin.get_history(person_id, key)
            )
            st.session_state.count += 1
            store.save_response({
                "time": datetime.now().isoformat(timespec="seconds"),
                "person_id": person_id,
                "person_name": person.name,
                "email_id": email["id"],
                "cue": email["cue"],
                "label": email["label"],
                "said": "spam" if said_spam else "not spam",
                "truth": "spam email" if email["label"] == "phishing" else "real email",
                "correct": twin.get_history(person_id)[-1]["correct"],
                "action": action,
            })
            st.session_state.pos += 1
            st.rerun()

    with right:
        fb = st.session_state.last_feedback
        st.subheader("Feedback")
        if not fb:
            st.caption("Answer an email and the feedback appears here.")
        else:
            if fb["outcome"] in ("caught", "fine"):
                st.success(fb["headline"])
            elif fb["outcome"] == "missed":
                st.error(fb["headline"])
            else:
                st.warning(fb["headline"])

            if fb.get("technique"):
                st.markdown("**Technique:** %s" % fb["technique"])
            if fb["tells"]:
                st.markdown("**%s:**" %
                            ("What gave it away" if fb["was"] == "phishing" else "Why it was safe"))
                for tell in fb["tells"]:
                    st.markdown("- %s" % tell)
            if fb.get("hidden_link"):
                text, target = fb["hidden_link"]
                st.markdown("**The link said** `%s` **but went to** `%s`" % (text, target))
            if fb.get("reply_to"):
                st.markdown("**Reply-To was** `%s`" % fb["reply_to"])
            if fb.get("defense"):
                st.info("**Key defense:** %s" % fb["defense"])
            if fb.get("history_note"):
                st.markdown("**History:** %s" % fb["history_note"])


# ====================================================================== PERSON

with tab_person:
    st.subheader(person.name)
    st.caption("%s  ·  %s  ·  %s" % (person.id, person.job_title, person.department))

    records = twin.get_history(person_id)
    judged = [r for r in records if "correct" in r]

    if not judged:
        st.info(
            "%s has not been asked anything yet. Use the **Inbox** tab to ask "
            "them, or the **Run** tab to let the simulation do it." % person.name
        )
    else:
        sc = twin.get_score(person_id)

        # ---- one line, the whole result ----
        st.markdown("### Asked %d questions — got %d correct and %d incorrect  (%.0f%%)"
                    % (sc["answered"], sc["correct"], sc["wrong"], 100 * sc["accuracy"]))

        # ---- accuracy split by what the email actually was ----
        # One overall number hides the important asymmetry: someone who calls
        # everything "real" scores well on genuine mail and terribly on spam.
        spam_total = sc["spam_seen"]
        real_total = sc["genuine_seen"]
        spam_right = spam_total - sc["missed_spam"]
        real_right = real_total - sc["false_alarms"]

        a1, a2, a3 = st.columns(3)
        a1.metric(
            "On spam emails",
            "%.0f%%" % (100 * spam_right / spam_total) if spam_total else "-",
            help="How often they correctly flagged a fake as spam.",
        )
        a2.metric(
            "On real emails",
            "%.0f%%" % (100 * real_right / real_total) if real_total else "-",
            help="How often they correctly trusted a genuine email.",
        )
        a3.metric("Overall", "%.0f%%" % (100 * sc["accuracy"]))
        st.caption(
            "Spam: %d of %d correct  ·  Real: %d of %d correct. "
            "The %d they got wrong split into %d fakes trusted and "
            "%d genuine emails flagged."
            % (spam_right, spam_total, real_right, real_total,
               sc["wrong"], sc["missed_spam"], sc["false_alarms"])
        )

        # ---- one table: every question, what it was, what they said ----
        rows = []
        for r in judged:
            rows.append({
                "#": r["n"],
                "email": str(r["email_id"]),
                "subject": r["subject"],
                "really was": r["truth"],
                "they said": r["said"],
                "result": "correct" if r["correct"] else "INCORRECT",
            })
        qdf = pd.DataFrame(rows)

        show = st.radio("Show", ["All questions", "Only wrong", "Only correct"],
                        horizontal=True, label_visibility="collapsed")
        if show == "Only wrong":
            view = qdf[qdf["result"] == "INCORRECT"]
        elif show == "Only correct":
            view = qdf[qdf["result"] == "correct"]
        else:
            view = qdf

        st.dataframe(view, width='stretch', hide_index=True, height=330)
        st.caption(
            "%d of the mistakes were spam they trusted; %d were real emails they "
            "flagged as spam." % (sc["missed_spam"], sc["false_alarms"])
        )

        # ---- read the actual email that was tested ----
        st.divider()
        st.markdown("**See the actual email that was tested**")

        by_id = {e["id"]: e for e in emails}
        by_id.update({e["id"]: e for e in st.session_state.generated})
        options = list(dict.fromkeys(r["email_id"] for r in reversed(judged)))
        labels = {}
        for r in reversed(judged):
            if r["email_id"] not in labels:
                mark = "correct" if r["correct"] else "INCORRECT"
                labels[r["email_id"]] = "%s  —  %s  (%s)" % (
                    r["email_id"], r["subject"][:52], mark)

        pick = st.selectbox("Pick an email", options,
                            format_func=lambda i: labels.get(i, i),
                            label_visibility="collapsed")

        e = by_id.get(pick)
        if e:
            answers = [r for r in judged if r["email_id"] == pick]
            last = answers[-1]

            ec1, ec2 = st.columns([3, 2])
            with ec1:
                st.markdown("**From:** %s `<%s>`"
                            % (e.get("sender_name", "?"), e["sender_email"]))
                if e.get("reply_to"):
                    st.markdown("**Reply-To:** `%s`" % e["reply_to"])
                st.markdown("**Subject:** %s" % e["subject"])
                st.text_area("Body", e["body"], height=220,
                             disabled=True, label_visibility="collapsed")
            with ec2:
                if last["correct"]:
                    st.success("Said **%s** — this really was a **%s**. Correct."
                               % (last["said"], last["truth"]))
                else:
                    st.error("Said **%s** — but this was a **%s**. Wrong."
                             % (last["said"], last["truth"]))

                if e["label"] == "phishing":
                    st.markdown("**Technique:** %s" % e.get("technique", "-"))
                    st.markdown("**What gave it away:**")
                    for flag in e.get("red_flags", []):
                        st.markdown("- %s" % flag)
                else:
                    st.markdown("**Why it was safe:**")
                    for sign in e.get("safe_signs", []):
                        st.markdown("- %s" % sign)

        # ---- the counters, tucked away ----
        with st.expander("Counters and full history"):
            totals = twin.get_totals(person_id)
            st.dataframe(
                pd.DataFrame([
                    {"cue": c, "yes": totals[c]["yes"], "no": totals[c]["no"],
                     "all": totals[c]["all"], "P(click)": totals[c]["p_click"]}
                    for c in CUES
                ]),
                width='stretch', hide_index=True,
            )
            st.caption("yes = trusted spam · no = flagged it · P(click) = yes / all")
            st.dataframe(
                pd.DataFrame([
                    {"#": r["n"], "email": str(r["email_id"]), "cue": r["cue"],
                     "they said": r["said"], "really was": r["truth"],
                     "result": "correct" if r.get("correct") else "incorrect",
                     "source": r["source"]}
                    for r in reversed(records)
                ]),
                width='stretch', hide_index=True, height=260,
            )


# ================================================================= ALL HISTORY

with tab_history:
    st.subheader("History")

    # Flat table: who, which email, what it was, what they said.
    all_rows, summary = [], []
    for idx, p in enumerate(people, start=1):
        events = [r for r in twin.get_history(p.id) if "correct" in r]
        if not events:
            continue
        ok = sum(1 for r in events if r["correct"])
        summary.append({
            "tag": "T%d" % idx,
            "person": p.name,
            "id": p.id,
            "Q": len(events),
            "correct": ok,
            "incorrect": len(events) - ok,
            "accuracy": "%d%%" % round(100 * ok / len(events)),
        })
        for r in events:
            all_rows.append({
                "id": r["n"],
                "person": p.id,
                "email_id": str(r["email_id"]),
                "subject": r["subject"],
                "label": "spam" if r["label"] == "phishing" else "real",
                "answer": "spam" if r["said"] == "spam" else "real",
                "correct": r["correct"],
                "probability": r["p_click"],
            })

    if not all_rows:
        st.info("Nothing yet. Use the **Run** tab or answer some in **Inbox**.")
    else:
        # ---- the headline, one line per person ----
        st.markdown("**Results**")
        for s in summary:
            st.markdown("**%s** (%s) — %d Q, :blue[%d correct], :red[%d incorrect]  ·  %s"
                        % (s["tag"], s["person"], s["Q"], s["correct"],
                           s["incorrect"], s["accuracy"]))

        st.divider()

        adf = pd.DataFrame(all_rows)

        f1, f2 = st.columns([3, 2])
        with f1:
            who = st.multiselect("Person", options=sorted(adf["person"].unique()),
                                 placeholder="Everyone")
        with f2:
            res = st.radio("Show", ["All", "Only wrong", "Only correct"], horizontal=True)

        view = adf
        if who:
            view = view[view["person"].isin(who)]
        if res == "Only wrong":
            view = view[~view["correct"]]
        elif res == "Only correct":
            view = view[view["correct"]]

        st.caption("%d of %d answers." % (len(view), len(adf)))
        st.dataframe(view, width='stretch', hide_index=True, height=420)

        st.download_button("Download CSV", data=view.to_csv(index=False),
                           file_name="history.csv", mime="text/csv")
        st.caption("Same columns as `data/history.csv`, which is written automatically.")


# ========================================================================= RUN

with tab_run:
    st.subheader("Run the simulation")
    st.caption(
        "Each delivery picks a random person and a random email. They judge it "
        "spam or not, and the result lands in the history."
    )

    r1, r2, r3 = st.columns([2, 2, 3])
    with r1:
        deliveries = st.number_input(
            "Emails to deliver", min_value=1, max_value=1000000,
            value=1000, step=1,
            help="Type any number from 1 to 1,000,000.")
    with r2:
        who = st.radio("Send to", ["Everyone (random)", "Just %s" % person.name])
    with r3:
        mode = ("reading the email - no hidden numbers"
                if st.session_state.get("use_reader", True)
                else ":red[hidden_probs + dice]")
        st.caption("Answers come from %s." % mode)
        if who.startswith("Everyone"):
            st.caption("Spread over %d people, so %d deliveries is roughly "
                       "%d each." % (len(people), deliveries,
                                     deliveries // len(people)))
        else:
            st.caption("All %d go to %s. Change who in the sidebar."
                       % (deliveries, person.name))

    if st.button("Run now", type="primary"):
        emails_by_id = {e["id"]: e for e in emails}
        emails_by_id.update({e["id"]: e for e in st.session_state.generated})
        allow_repeats = st.session_state.get("allow_repeats", True)
        build_new = st.session_state.get("build_new", True)

        progress = st.progress(0.0, text="Delivering...")
        total = int(deliveries)

        # Either spread across everyone, or all to the person selected
        # in the sidebar.
        targets = people if who.startswith("Everyone") else [person]

        # The same engine the Live tab drives, just without drawing each
        # arrival. Live and Run used to hold two copies of this loop.
        generated = st.session_state.generated
        before = len(generated)
        delivered, skipped = get_engine().deliver_many(
            total, targets=targets, build_new=build_new,
            allow_repeats=allow_repeats, generated=generated,
            on_progress=lambda n, t: progress.progress(
                n / t, text="Delivered %d of %d" % (n, t)),
        )
        if len(generated) > before:
            st.session_state.generated_dirty = True

        twin.save(people_by_id=people_by_id)
        if st.session_state.get("generated_dirty"):
            store.save_generated(st.session_state.generated)
            st.session_state.generated_dirty = False
        emails_by_id.update({e["id"]: e for e in st.session_state.generated})
        twin.write_email_scores(emails_by_id)
        progress.empty()

        note = ("Delivered %d emails to %s. All CSVs updated."
                % (delivered, "%d people" % len(targets) if len(targets) > 1
                   else person.name))
        if skipped:
            note += (" %d skipped - those people had already seen every email "
                     "(turn on Allow repeats)." % skipped)
        st.success(note)
        st.rerun()

    auto = st.session_state.get("auto_results")
    if auto:
        st.divider()
        st.markdown("**Last run for %s**" % auto["person"])
        a1, a2, a3, a4 = st.columns(4)
        a1.metric("Clicked", "%.0f%%" % (100 * auto["click_rate"]))
        a2.metric("Recognised", "%.0f%%" % (100 * auto["report_rate"]))
        a3.metric("Ignored", "%.0f%%" % (100 * auto["ignore_rate"]))
        a4.metric("Twin error", "%.3f" % auto["avg_error"])
        st.caption(
            "Twin error is the gap between its guesses and the hidden probabilities. "
            "Those are read only to grade the twin - the twin never sees them."
        )


# ======================================================================= MODEL

with tab_model:
    st.subheader("Test the model on brand new emails")
    st.caption(
        "Builds emails nobody has seen, then asks both models to predict how "
        "each of the 25 people would do - and checks them against what those "
        "people actually do."
    )

    m1, m2 = st.columns([2, 4])
    with m1:
        n_new = st.number_input("New emails to build", 10, 2000, 200, step=10)
    with m2:
        st.caption(
            "Each email is built from a genuine one plus modifications "
            "(forged sender, hidden link, urgency, misspelling, and the rest). "
            "The red flags come from the modifications, not by hand."
        )
        st.caption("%d emails x 25 people = %d predictions."
                   % (n_new, n_new * len(people)))

    if st.button("Build and test", type="primary"):
        answers = sum(len(twin.get_history(p.id)) for p in people)
        progress = st.progress(0.0, text="Training on %d past answers..." % answers)
        try:
            # benchmark.py does the whole comparison: train, build the new
            # emails, score both models, grade them against the reader.
            rdf = benchmark.run(
                int(n_new), twin=twin, people=people,
                on_progress=lambda i, total, name: progress.progress(
                    i / total, text="%s (%d/%d)" % (name, i, total)),
            )
            st.session_state.model_results = rdf
            st.session_state.model_n = int(n_new)
        except Exception as exc:
            st.error("Could not run the comparison: %s" % exc)
        progress.empty()

    rdf = st.session_state.get("model_results")
    if rdf is not None and len(rdf):
        st.divider()
        st.markdown("### Results on %d new emails"
                    % st.session_state.get("model_n", 0))

        summary = benchmark.summarise(rdf)
        c1, c2, c3 = st.columns(3)
        c1.metric("Machine learning model", "%.1f%%" % summary["ml"])
        c2.metric("Counting twin  a/(a+b)", "%.1f%%" % summary["twin"])
        c3.metric("Difference", "%+.1f pts" % summary["difference"])
        st.caption("%d predictions. Ratio = how often the prediction matched "
                   "what the person actually did." % len(rdf))

        b1, b2 = st.columns(2)
        with b1:
            st.markdown("**By awareness**")
            by = rdf.groupby("awareness")[["ml_right", "twin_right"]].mean() * 100
            by.columns = ["ML (%)", "Twin (%)"]
            st.dataframe(by.round(1), width='stretch')
        with b2:
            st.markdown("**Hardest techniques to predict**")
            byt = (rdf.groupby("technique")[["ml_right"]].mean() * 100)
            byt.columns = ["ML (%)"]
            st.dataframe(byt.round(1).sort_values("ML (%)"), width='stretch',
                         height=240)

        st.markdown("**Where the ML model went wrong**")
        w1, w2 = st.columns(2)
        w1.metric("Expected to catch it, but fell", summary["missed"])
        w2.metric("Expected to fall, but caught it", summary["over"])
        st.caption(
            "Under-predicting failure is the riskier error: those are people "
            "the model would not have flagged for training."
        )

        with st.expander("Every prediction"):
            st.dataframe(rdf, width='stretch', hide_index=True, height=360)
            st.download_button("Download CSV", rdf.to_csv(index=False),
                               file_name="model_predictions.csv", mime="text/csv")


# ====================================================================== EMAILS

with tab_emails:
    # ---- generate a brand new one on demand ----
    st.subheader("Generate a new email")
    st.caption(
        "Takes a genuine email, swaps every entity in it for a fresh value "
        "(reference numbers, days, times, wards, extensions), then applies "
        "the phishy modifications. Checked against everything already made, "
        "and rebuilt if it is too close."
    )

    g1, g2, g3 = st.columns([2, 2, 3])
    with g1:
        gen_type = st.selectbox("Email type", ["Any"] + sorted(GEN_RECIPES))
    with g2:
        gen_count = st.number_input("How many", 1, 500, 1, step=1)
    with g3:
        st.caption("Saved to `%s` - a new row each time, never the static file."
                   % GEN_CSV)

    if st.button("Generate", type="primary"):
        maker = EmailGeneratorLLM()
        made, rejected = [], 0
        for _ in range(int(gen_count)):
            e = maker.generate(None if gen_type == "Any" else gen_type)
            if e:
                made.append(e)
            else:
                rejected += 1
        st.session_state.last_generated = made
        if made:
            st.success("Generated %d. %s"
                       % (len(made),
                          "%d rejected as too similar." % rejected if rejected
                          else "None were duplicates."))
        else:
            st.warning("Everything built was too close to something existing.")

    for e in (st.session_state.get("last_generated") or [])[:3]:
        with st.container(border=True):
            st.markdown("**%s** · %s · built from `%s` · %d attempt(s)"
                        % (e["id"], e["technique"], e["built_from"], e["attempts"]))
            st.markdown("**From:** `%s`" % e["sender_email"])
            if e.get("reply_to"):
                st.markdown("**Reply-To:** :red[`%s`]" % e["reply_to"])
            st.markdown("**Subject:** %s" % e["subject"])
            st.text_area("b", e["body"], height=170, disabled=True,
                         label_visibility="collapsed", key="gen_%s" % e["id"])
            x1, x2 = st.columns(2)
            with x1:
                st.markdown("**Entities swapped**")
                for k, v in e["entities_used"].items():
                    st.markdown("- `%s` -> %s" % (k, v))
            with x2:
                st.markdown("**Modifications**")
                for m in e["modifications"]:
                    st.markdown("- `%s`" % m)

    if os.path.exists(GEN_CSV):
        with open(GEN_CSV) as _f:
            st.download_button("Download generated_emails.csv", _f.read(),
                               file_name="generated_emails.csv", mime="text/csv")

    st.divider()
    st.subheader("The emails")
    st.caption(
        "The 51 originals, and every one built on the fly during live "
        "delivery. For a built email you can see exactly what was changed."
    )

    generated = st.session_state.get("generated", [])

    # The value is a fixed word and the count only goes in the label. With
    # the count in the option itself, every new email changed the option
    # text, so the stored choice matched nothing and the pool silently
    # flipped back to the curated set.
    src_choice = st.radio(
        "Show", ["built", "original"], horizontal=True, key="email_pool",
        format_func=lambda k: ("Built on the fly (%d)" % len(generated)
                               if k == "built" else "The original %d" % len(emails)),
    )
    showing_built = src_choice == "built"
    pool = generated if showing_built else emails

    if not pool:
        st.info(
            "None built yet. Turn on **Build new emails** in the sidebar and "
            "run **Live** or **Run**."
        )
    else:
        # ---- the list ----
        listing = pd.DataFrame([{
            # str() because ids are a mix of "E01" and integers, and a table
            # column has to be one type.
            "id": str(e["id"]),
            "technique": e.get("technique") or "-",
            "cue": e.get("cue") or "-",
            "sender": e.get("sender_email", ""),
            "subject": e.get("subject", ""),
            "changes": len(e.get("modifications", [])) if showing_built else "-",
        } for e in pool[-500:]])

        st.caption("Showing the most recent %d." % len(listing)
                   if len(pool) > 500 else "%d emails." % len(pool))
        st.dataframe(listing, width='stretch', hide_index=True, height=240)

        # ---- one email in full ----
        st.divider()
        ids = [e["id"] for e in pool[-500:]]
        labels = {e["id"]: "%s - %s" % (e["id"], e.get("subject", "")[:54])
                  for e in pool[-500:]}
        # A stable key, and labels that cannot collide: two emails can share
        # a subject, and without the id in the value the widget loses track
        # of which one was open whenever the pool grows.
        pick = st.selectbox("Open one", ids[::-1], key="open_email",
                            format_func=lambda i: labels.get(i, str(i)))
        chosen = next((e for e in pool if e["id"] == pick), None)

        if chosen:
            c1, c2 = st.columns([3, 2])

            with c1:
                st.markdown("**From:** %s `<%s>`"
                            % (chosen.get("sender_name", "?"),
                               chosen.get("sender_email", "")))
                if chosen.get("reply_to"):
                    st.markdown("**Reply-To:** :red[`%s`]" % chosen["reply_to"])
                st.markdown("**Subject:** %s" % chosen.get("subject", ""))
                st.text_area("Body", chosen.get("body", ""), height=300,
                             disabled=True, label_visibility="collapsed",
                             key="emailtab_body_%s" % pick)

            with c2:
                st.markdown("**What it is**")
                st.markdown("- Technique: **%s**" % (chosen.get("technique") or "-"))
                st.markdown("- Pressure: `%s`" % (chosen.get("cue") or "-"))
                st.markdown("- Address trick: `%s`"
                            % (chosen.get("address_trick") or "-"))
                st.markdown("- Difficulty: `%s`" % (chosen.get("difficulty") or "-"))

                if chosen.get("link_target"):
                    st.markdown("**The link**")
                    st.markdown("Reads `%s`" % chosen.get("link_text", "?"))
                    st.markdown("Goes to :red[`%s`]" % chosen["link_target"])

                if chosen.get("modifications"):
                    st.markdown("**Changes applied (%d)**"
                                % len(chosen["modifications"]))
                    for m in chosen["modifications"]:
                        mod = MODS.BY_NAME.get(m)
                        st.markdown("- `%s` - %s"
                                    % (m, mod.explains if mod else ""))

                st.markdown("**Red flags**")
                for f in chosen.get("red_flags", chosen.get("safe_signs", [])):
                    st.markdown("- %s" % f)

            # ---- before and after ----
            if chosen.get("built_from"):
                base = next((e for e in emails
                             if e["id"] == chosen["built_from"]), None)
                if base:
                    st.divider()
                    st.markdown("**Before and after** - built from the genuine "
                                "email `%s`" % base["id"])
                    d1, d2 = st.columns(2)
                    with d1:
                        st.markdown(":blue[**Genuine original**]")
                        st.markdown("**From:** `%s`" % base.get("sender_email", ""))
                        st.markdown("**Reply-To:** `%s`"
                                    % (base.get("reply_to") or "none"))
                        st.text_area("orig", base.get("body", ""), height=240,
                                     disabled=True, label_visibility="collapsed",
                                     key="emailtab_orig_%s" % pick)
                    with d2:
                        st.markdown(":red[**After the changes**]")
                        st.markdown("**From:** `%s`" % chosen.get("sender_email", ""))
                        st.markdown("**Reply-To:** `%s`"
                                    % (chosen.get("reply_to") or "none"))
                        st.text_area("made", chosen.get("body", ""), height=240,
                                     disabled=True, label_visibility="collapsed",
                                     key="emailtab_made_%s" % pick)

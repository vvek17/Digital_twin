"""Existing instructor views extracted from app.py."""

import pandas as pd
import streamlit as st

from backend.metrics import CUES, workforce_frame
from frontend.tables import PCT_BAR, show_table
from frontend.dashboard_charts import staff_chart, pressure_chart
from frontend.recognition_chart import recognition_chart, recognition_data
from frontend.layout import card, columns
from frontend.practice_views import render_assignment


def breakdown_label(value):
    """Readable labels only; source category IDs and calculations stay intact."""
    return {"it_login": "IT login", "hr_payroll": "HR / payroll"}.get(
        value, str(value).replace("_", " ").capitalize())


def render_dashboard(service, workspace, person_id):
    service.require_admin()
    wf = workforce_frame(workspace.twin, workspace.people)
    seen_total = int(wf["seen"].sum())
    if seen_total == 0:
        if any(workspace.twin.get_score(p.id)["answered"] for p in workspace.people):
            with card("Spam judgements per person", key="card_judgements"):
                _judgements_panel(workspace, wf)
        else:
            st.info("No history yet. Answer emails in Inbox or start an experiment in Run.")
        return
    clicked_total = int(wf["clicked"].sum())
    reported_total = int(wf["reported"].sum())
    with st.container(key="dashboard_metrics"):
        c1, c2, c3, c4 = columns(4, key="dashboard_metrics", kind="metrics")
        c1.metric("Phishing delivered", "%d" % seen_total)
        c2.metric("Clicked", "%.0f%%" % (100 * clicked_total / seen_total))
        c3.metric("Recognised", "%.0f%%" % (100 * reported_total / seen_total))
        c4.metric("Staff tracked", "%d" % int((wf["seen"] > 0).sum()))

    ranked = wf[wf["seen"] > 0].sort_values("click_rate", ascending=False)
    # Stack the compact pressure panel in the shorter column. This avoids
    # the empty half-screen left by a tall staff chart beside a short summary.
    pressure_on_left = len(ranked) < 8
    left, right = columns(key="dashboard")
    with left:
        with card("Who clicks", "Phishing clicked by person · colour shows awareness.", key="dashboard_clicks"):
            with st.container(key="staff_plot"):
                st.altair_chart(staff_chart(ranked), width="stretch")
            if len(ranked) > 16:
                st.caption("Scroll the chart for more people, or use its fullscreen control.")
        if pressure_on_left:
            with card("What works on people", key="dashboard_breakdown"):
                _pressure_panel(workspace)
    with right:
        with card("Clicked vs recognised", "Share of phishing delivered to each awareness group.",
                  key="dashboard_recognition"):
            comparison = recognition_data(wf)
            if comparison.empty:
                st.info("No phishing deliveries to compare yet.")
            else:
                st.altair_chart(recognition_chart(comparison),
                                width="content" if comparison["awareness"].nunique() > 4 else "stretch")
        if not pressure_on_left:
            with card("What works on people", key="dashboard_breakdown"):
                _pressure_panel(workspace)
    with card("Spam judgements per person", key="card_judgements"):
        _judgements_panel(workspace, wf)


def _pressure_panel(workspace):
    people, emails, twin = workspace.people, workspace.emails, workspace.twin
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
    dim = st.selectbox("Break down by", list(BREAKDOWNS), key="breakdown_dimension",
                       label_visibility="collapsed")
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
        agg["display_type"] = agg["type"].map(breakdown_label)

        with st.container(key="pressure_plot"):
            st.altair_chart(pressure_chart(agg), width="stretch")

        with st.expander("%s table" % dim):
            out = agg[["type", "asked", "fooled", "rate"]].rename(
                columns={"type": dim.lower(), "fooled": "trusted it"}).copy()
            out[dim.lower()] = out[dim.lower()].map(breakdown_label)
            out["rate"] = (100 * out["rate"]).round(0)
            show_table(out, height=420, font_weight=300, config={
                dim.lower(): st.column_config.TextColumn(dim),
                "asked": st.column_config.NumberColumn("Sent", help="Phishing emails delivered"),
                "trusted it": st.column_config.NumberColumn("Trusted", help="Emails treated as legitimate"),
                "rate": PCT_BAR("Trusted (%)", color="red"),
            })


def _judgements_panel(workspace, wf):
    people, twin = workspace.people, workspace.twin
    scores = []
    delivery_rows = wf.set_index("id").to_dict("index")
    for p in people:
        sc = twin.get_score(p.id)
        if sc["answered"]:
            delivery = delivery_rows[p.id]
            scores.append({
                "id": p.id, "name": p.name, "role": p.job_title,
                "awareness": p.security_awareness,
                "phishing seen": delivery["seen"], "clicked": delivery["clicked"],
                "reported": delivery["reported"],
                "click rate": round(100 * delivery["click_rate"]),
                "report rate": round(100 * delivery["report_rate"]),
                "judged": sc["answered"], "correct": sc["correct"],
                "incorrect": sc["wrong"],
                "accuracy": round(100 * sc["accuracy"]),
                "spam trusted": sc["missed_spam"],
                "genuine flagged": sc["false_alarms"],
            })
    if scores:
        st.caption(
            "How many each person judged, and how many they got right. "
            "The last two columns split the mistakes: spam they trusted "
            "versus genuine mail they flagged."
        )
        sdf = pd.DataFrame(scores).sort_values("accuracy", ascending=False)
        basic = ["name", "judged", "correct", "incorrect", "accuracy",
                 "spam trusted", "genuine flagged"]
        with st.expander("Choose columns"):
            st.caption("One table combines judgement scores and delivery details. "
                       "Click/report rates use phishing deliveries only.")
            visible = st.multiselect("Visible columns", list(sdf.columns), default=basic,
                                    key="dashboard_columns")
        show_table(sdf[visible or basic], height=420, config={
            "id": st.column_config.TextColumn("ID"),
            "name": st.column_config.TextColumn("Person"),
            "awareness": st.column_config.TextColumn("Awareness"),
            "role": st.column_config.TextColumn("Role"),
            "phishing seen": st.column_config.NumberColumn("Phishing seen"),
            "click rate": PCT_BAR("Clicked (%)"),
            "report rate": PCT_BAR("Recognised"),
            "judged": st.column_config.NumberColumn("Judged"),
            "correct": st.column_config.NumberColumn("Correct"),
            "incorrect": st.column_config.NumberColumn("Incorrect"),
            "accuracy": PCT_BAR("Accuracy"),
            "spam trusted": st.column_config.NumberColumn(
                "Spam trusted", help="Fakes they believed - the costly mistake"),
            "genuine flagged": st.column_config.NumberColumn(
                "Genuine flagged", help="Real mail they reported"),
        })


def render_person(service, workspace, person_id):
    service.require_admin()
    people, emails, twin = workspace.people, workspace.emails, workspace.twin
    people_by_id = workspace.people_by_id
    person = people_by_id[person_id]
    st.subheader(person.name)
    st.caption("%s  ·  %s  ·  %s" % (person.id, person.job_title, person.department))
    render_assignment(service, workspace, person_id)

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
        st.caption("Asked %d questions — got %d correct and %d incorrect  (%.0f%%)"
                    % (sc["answered"], sc["correct"], sc["wrong"], 100 * sc["accuracy"]))

        # ---- accuracy split by what the email actually was ----
        # One overall number hides the important asymmetry: someone who calls
        # everything "real" scores well on genuine mail and terribly on spam.
        spam_total = sc["spam_seen"]
        real_total = sc["genuine_seen"]
        spam_right = spam_total - sc["missed_spam"]
        real_right = real_total - sc["false_alarms"]

        a1, a2, a3 = columns(3, key="person_scores", kind="metrics")
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

        show_table(view, height=520, config={
            "#": st.column_config.NumberColumn("#"),
            "email": st.column_config.TextColumn("Email"),
            "subject": st.column_config.TextColumn("Subject"),
            "really was": st.column_config.TextColumn("Really was"),
            "they said": st.column_config.TextColumn("They said"),
            "result": st.column_config.TextColumn("Result"),
        })
        st.caption(
            "%d of the mistakes were spam they trusted; %d were real emails they "
            "flagged as spam." % (sc["missed_spam"], sc["false_alarms"])
        )

        # ---- read the actual email that was tested ----
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

        # A label the widget has not seen falls back to the id itself, and an
        # id is an int, which Streamlit cannot render. str() keeps it a string.
        pick = st.selectbox("Pick an email", options,
                            format_func=lambda i: str(labels.get(i, i)),
                            label_visibility="collapsed")

        e = by_id.get(pick)
        if e:
            answers = [r for r in judged if r["email_id"] == pick]
            last = answers[-1]

            ec1, ec2 = columns(key="person_email")
            with ec1, card("Email", key="card_person_email"):
                st.markdown("**From:** %s `<%s>`"
                            % (e.get("sender_name", "?"), e["sender_email"]))
                if e.get("reply_to"):
                    st.markdown("**Reply-To:** `%s`" % e["reply_to"])
                st.markdown("**Subject:** %s" % e["subject"])
                st.text_area("Body", e["body"], height=220,
                             disabled=True, label_visibility="collapsed")
            with ec2, card("Judgement", key="card_person_judgement"):
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
            show_table(
                pd.DataFrame([
                    {"cue": c, "yes": totals[c]["yes"], "no": totals[c]["no"],
                     "all": totals[c]["all"], "P(click)": totals[c]["p_click"]}
                    for c in CUES
                ]),
            )
            st.caption("yes = trusted spam · no = flagged it · P(click) = yes / all")
            show_table(pd.DataFrame([
                {"#": r["n"], "email": str(r["email_id"]), "cue": r["cue"],
                 "they said": r["said"], "really was": r["truth"],
                 "result": "correct" if r.get("correct") else "incorrect",
                 "source": r["source"]}
                for r in reversed(records)
            ]), height=400)

def render_history(service, workspace, person_id):
    service.require_admin()
    people, emails, twin = workspace.people, workspace.emails, workspace.twin
    people_by_id = workspace.people_by_id
    person = people_by_id[person_id]

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
            "accuracy": round(100 * ok / len(events)),
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
        with st.expander("Per-person results"):
            show_table(pd.DataFrame(summary), config={
                "tag": st.column_config.TextColumn("Tag"),
                "person": st.column_config.TextColumn("Person"),
                "Q": st.column_config.NumberColumn("Judged"),
                "correct": st.column_config.NumberColumn("Correct"),
                "incorrect": st.column_config.NumberColumn("Incorrect"),
                "accuracy": PCT_BAR("Accuracy"),
            })

        adf = pd.DataFrame(all_rows)

        f1, f2 = columns(key="history_filters", kind="controls")
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
        show_table(view, height=560, config={
            "id": st.column_config.NumberColumn("#"),
            "person": st.column_config.TextColumn("Person"),
            "email_id": st.column_config.TextColumn("Email"),
            "subject": st.column_config.TextColumn("Subject"),
            "label": st.column_config.TextColumn("Really was"),
            "answer": st.column_config.TextColumn("They said"),
            "correct": st.column_config.CheckboxColumn("Correct"),
            "probability": st.column_config.NumberColumn(
                "P(click)", format="%.2f"),
        })

        st.download_button("Download CSV", data=view.to_csv(index=False),
                           file_name="history.csv", mime="text/csv")
        st.caption("Same columns as `data/history.csv`, which is written automatically.")

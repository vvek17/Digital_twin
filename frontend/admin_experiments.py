"""Existing instructor views extracted from app.py."""

import time
import altair as alt
import pandas as pd
import streamlit as st

from backend import benchmark
from frontend.tables import PCT_BAR, show_table
from frontend.theme import readable_chart, verdict_of
from frontend.runtime import reset_live
from frontend.layout import card, columns


def render_live(service, workspace, person_id):
    service.require_admin()
    people, emails, twin = workspace.people, workspace.emails, workspace.twin
    people_by_id = workspace.people_by_id
    person = people_by_id[person_id]
    st.caption(
        "Emails arrive one at a time to random staff. Each line is one delivery "
        "and what that person did with it."
    )

    with st.container(horizontal=True, gap="small", vertical_alignment="bottom"):
        start = st.button("Start", type="primary", width="content",
                          disabled=st.session_state.live_running)
        stop = st.button("Stop", width="content",
                         disabled=not st.session_state.live_running)
        clear = st.button("Clear", width="content")
        with st.container(width=300):
            delay = st.select_slider("Speed (seconds per email)",
                                     options=[0.0, 0.1, 0.25, 0.5, 1.0], value=0.25)

    if start:
        st.session_state.live_running = True
    if stop:
        st.session_state.live_running = False
        service.save_workspace(workspace)
    if clear:
        reset_live(workspace)
        st.rerun()

    status = st.empty()
    latest_box = st.empty()
    trace_box = st.empty()
    feed_column, boards_column = columns(key="live_feed")
    with feed_column:
        feed_box = st.empty()
    with boards_column:
        boards_box = st.empty()

    def render_live():
        feed = st.session_state.live_feed
        stats = st.session_state.live_stats

        with status.container():
            m1, m2, m3, m4 = columns(4, key="live_status_%d" % st.session_state.live_rounds, kind="metrics")
            seen = sum(s["seen"] for s in stats.values())
            clicked = sum(s["clicked"] for s in stats.values())
            reported = sum(s["reported"] for s in stats.values())
            m1.metric("Delivered", st.session_state.live_rounds)
            m2.metric("Phishing", seen)
            m3.metric("Clicked", "%.0f%%" % (100 * clicked / seen) if seen else "-")
            m4.metric("Recognised", "%.0f%%" % (100 * reported / seen) if seen else "-")

        # ---- the email that just landed, exactly as that person saw it ----
        with latest_box.container(border=bool(feed)):
            if feed:
                rec = feed[0]
                e = rec["email"]
                label, colour = verdict_of(rec)
                head, side = columns(key="live_email_%d" % st.session_state.live_rounds)

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
                        t1, t2, t3 = columns(3, key="live_counters_%d" % st.session_state.live_rounds, kind="metrics")
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
        with trace_box.container(border=len(st.session_state.live_trace) > 4):
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
                    .properties(height=180)
                )
                st.altair_chart(
                    readable_chart(line),
                    width='stretch',
                )
                st.caption("One line per cue, for whichever person each email landed on.")

        with feed_box.container(border=True, height=460 if feed else "content"):
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
                b1, b2 = st.container(), st.container()
                with b1:
                    st.markdown(":red[**Who clicks**]")
                    top = sorted(ranked, key=lambda s: -s["clicked"] / s["seen"])[:8]
                    show_table(pd.DataFrame([{
                        "person": s["name"], "awareness": s["awareness"],
                        "seen": s["seen"],
                        "clicked": round(100 * s["clicked"] / s["seen"]),
                    } for s in top]), height=210, visible=["person", "clicked"], config={
                        "person": st.column_config.TextColumn("Person"),
                        "awareness": st.column_config.TextColumn("Aware"),
                        "seen": st.column_config.NumberColumn("Seen"),
                        "clicked": PCT_BAR("Clicked"),
                    })
                with b2:
                    st.markdown(":blue[**Who knows**]")
                    top = sorted(ranked, key=lambda s: -s["reported"] / s["seen"])[:8]
                    show_table(pd.DataFrame([{
                        "person": s["name"], "awareness": s["awareness"],
                        "seen": s["seen"],
                        "recognised": round(100 * s["reported"] / s["seen"]),
                    } for s in top]), height=210, visible=["person", "recognised"], config={
                        "person": st.column_config.TextColumn("Person"),
                        "awareness": st.column_config.TextColumn("Aware"),
                        "seen": st.column_config.NumberColumn("Seen"),
                        "recognised": PCT_BAR("Recognised"),
                    })

    render_live()

    # Run a short burst, then rerun so the Stop button can register. Streamlit
    # is single-threaded: a long blocking loop would ignore every click.
    if st.session_state.live_running:
        BURST = 12
        for _ in range(BURST):
            rec = live_step(service, workspace)
            if rec is None:
                st.session_state.live_running = False
                st.warning("No unseen generated emails are available. Generate emails in Emails, "
                           "turn on Build new emails, or allow repeats of the saved generated pool.")
                break
            st.session_state.live_feed.insert(0, rec)
            del st.session_state.live_feed[10:]
            render_live()
            if delay:
                time.sleep(delay)
        service.save_workspace(workspace, generated=True)
        st.session_state.generated_dirty = False
        st.rerun()


def render_run(service, workspace, person_id):
    service.require_admin()
    people, emails, twin = workspace.people, workspace.emails, workspace.twin
    people_by_id = workspace.people_by_id
    person = people_by_id[person_id]
    st.caption(
        "Each delivery picks a random person and a random email. They judge it "
        "spam or not, and the result lands in the history."
    )

    setup, details = columns(key="run_setup")
    with setup, card("Delivery setup", key="card_run_setup"):
        deliveries = st.number_input(
            "Emails to deliver", min_value=1, max_value=1000000,
            value=1000, step=1,
            help="Type any number from 1 to 1,000,000.")
        who = st.radio("Send to", ["Everyone (random)", "Just %s" % person.name])
        start_run = st.button("Run now", type="primary")
    with details, card("Run summary", key="card_run_summary"):
        st.caption("Automatic answers come from reading the email; hidden probabilities are not used.")
        if who.startswith("Everyone"):
            st.caption("Spread over %d people, so %d deliveries is roughly "
                       "%d each." % (len(people), deliveries,
                                     deliveries // len(people)))
        else:
            st.caption("All %d go to %s. Change who in the sidebar."
                       % (deliveries, person.name))

    if start_run:
        st.session_state.run_running = True
        try:
            allow_repeats = st.session_state.get("allow_repeats", True)
            build_new = st.session_state.get("build_new", True)

            progress = st.progress(0.0, text="Delivering...")
            total = int(deliveries)

            # Either spread across everyone, or all to the person selected
            # in the sidebar.
            targets = people if who.startswith("Everyone") else [person]

            # The same engine the Live tab drives, just without drawing each
            # arrival. Live and Run used to hold two copies of this loop.
            delivered, skipped = service.run_many(
                workspace, total,
                targets=targets, build_new=build_new,
                allow_repeats=allow_repeats,
                on_progress=lambda n, t: progress.progress(
                    n / t, text="Delivered %d of %d" % (n, t)),
            )
            st.session_state.generated_dirty = False
            progress.empty()

            note = ("Delivered %d emails to %s. All CSVs updated."
                    % (delivered, "%d people" % len(targets) if len(targets) > 1
                       else person.name))
            if skipped:
                note += (" %d skipped - no unseen generated emails were available. "
                         "Generate emails in Emails, turn on Build new emails, or allow repeats "
                         "of an existing generated pool." % skipped)
            # Keep the completion message across the history-refresh rerun.
            st.session_state.run_note = note
            st.rerun()
        finally:
            st.session_state.run_running = False

    done = st.session_state.pop("run_note", None)
    if done:
        st.success(done)



def render_model(service, workspace, person_id):
    service.require_admin()
    people, emails, twin = workspace.people, workspace.emails, workspace.twin
    people_by_id = workspace.people_by_id
    person = people_by_id[person_id]
    st.warning("The model test has two scoring problems. It counts correct answers to safe "
               "emails as mistakes. In the command-line test, the counting model also sees "
               "the test answers beforehand. The model scores should not be trusted until "
               "these problems are fixed. Your manual Inbox scores are not affected.")
    st.caption(
        "Builds emails nobody has seen, then asks both models to predict how "
        "each of the 25 people would do - and checks them against what those "
        "people actually do."
    )

    m1, m2 = columns(key="model_setup")
    with m1, card("Test setup", key="card_model_setup"):
        n_new = st.number_input("New emails to build", 10, 2000, 200, step=10)
        test_model = st.button("Build and test", type="primary")
    with m2, card("What is tested", key="card_model_description"):
        st.caption(
            "Each email is built from a genuine one plus modifications "
            "(forged sender, hidden link, urgency, misspelling, and the rest). "
            "The red flags come from the modifications, not by hand."
        )
        st.caption("%d emails x 25 people = %d predictions."
                   % (n_new, n_new * len(people)))

    if test_model:
        answers = sum(len(twin.get_history(p.id)) for p in people)
        progress = st.progress(0.0, text="Training on %d past answers..." % answers)
        try:
            # benchmark.py does the whole comparison: train, build the new
            # emails, score both models, grade them against the reader.
            rdf = service.compare_models(
                workspace, int(n_new),
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
        st.markdown("### Results on %d new emails"
                    % st.session_state.get("model_n", 0))

        summary = benchmark.summarise(rdf)
        c1, c2, c3 = columns(3, key="model_summary", kind="metrics")
        c1.metric("Machine learning model", "%.1f%%" % summary["ml"])
        c2.metric("Counting twin  a/(a+b)", "%.1f%%" % summary["twin"])
        c3.metric("Difference", "%+.1f pts" % summary["difference"])
        st.caption("%d predictions. Ratio = how often the prediction matched "
                   "what the person actually did." % len(rdf))

        b1, b2 = columns(key="model_results")
        with b1, card("By awareness", key="card_model_awareness"):
            by = rdf.groupby("awareness")[["ml_right", "twin_right"]].mean() * 100
            by.columns = ["ML (%)", "Twin (%)"]
            show_table(by.round(1), height=200, index=True, config={
                "ML (%)": PCT_BAR("ML (%)"),
                "Twin (%)": PCT_BAR("Twin (%)"),
            })
        with b2, card("Hardest techniques to predict", key="card_model_techniques"):
            byt = (rdf.groupby("technique")[["ml_right"]].mean() * 100)
            byt.columns = ["ML (%)"]
            show_table(byt.round(1).sort_values("ML (%)"), height=420,
                       index=True, config={"ML (%)": PCT_BAR("ML (%)")})

        st.markdown("**Where the ML model went wrong**")
        w1, w2 = columns(key="model_errors", kind="metrics")
        w1.metric("Expected to catch it, but fell", summary["missed"])
        w2.metric("Expected to fall, but caught it", summary["over"])
        st.caption(
            "Under-predicting failure is the riskier error: those are people "
            "the model would not have flagged for training."
        )

        with st.expander("Every prediction"):
            show_table(rdf, height=520, config={
                "person": st.column_config.TextColumn("Person"),
                "awareness": st.column_config.TextColumn("Awareness"),
                "email": st.column_config.TextColumn("Email"),
                "technique": st.column_config.TextColumn("Attack type"),
                "ml_says_falls": st.column_config.CheckboxColumn("ML: falls"),
                "twin_says_falls": st.column_config.CheckboxColumn("Twin: falls"),
                "actually_fell": st.column_config.CheckboxColumn("Actually fell"),
                "ml_right": st.column_config.CheckboxColumn("ML right"),
                "twin_right": st.column_config.CheckboxColumn("Twin right"),
            })
            st.download_button("Download CSV", rdf.to_csv(index=False),
                               file_name="model_predictions.csv", mime="text/csv")


def live_step(service, workspace):
    """One delivery, plus the session-only tallies the boards read."""
    generated = st.session_state.generated
    before = len(generated)

    rec = service.deliver_one(
        workspace,
        build_new=st.session_state.get("build_new", True),
        allow_repeats=st.session_state.get("allow_repeats", True),
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

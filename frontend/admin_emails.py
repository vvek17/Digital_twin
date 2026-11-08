"""Existing instructor views extracted from app.py."""

import pandas as pd
import streamlit as st

from frontend.tables import show_table
from frontend.layout import card, columns

from backend.email_builder import RECIPES as GEN_RECIPES
from backend import modifications as MODS


def render_emails(service, workspace, person_id):
    service.require_admin()
    people, emails, twin = workspace.people, workspace.emails, workspace.twin
    people_by_id = workspace.people_by_id
    person = people_by_id[person_id]
    with card("Generate a new email", "Create variations from genuine emails; similar outputs are rejected.",
              key="card_email_generator"):
        type_col, count_col, action_col = columns(3, key="email_generator", kind="controls",
                                                 vertical_alignment="bottom")
        with type_col:
            gen_type = st.selectbox("Email type", ["Any"] + sorted(GEN_RECIPES))
        with count_col:
            gen_count = st.number_input("How many", 1, 500, 1, step=1)
        with action_col:
            generate = st.button("Generate", type="primary", width="stretch")
        with st.expander("How generation works"):
            st.caption("Takes a genuine email, replaces reference numbers, days, times, wards and "
                       "extensions, then applies phishing modifications and checks similarity. "
                       "Saved in the generated-email pool and CSV export, ready for assigned practice. "
                       "The original source emails stay unchanged.")
        if generate:
            with st.spinner("Generating emails…"):
                made, rejected = service.generate_emails(
                    workspace, int(gen_count), None if gen_type == "Any" else gen_type)
            st.session_state.last_generated = made
            if made:
                st.success("Generated %d. %s"
                           % (len(made),
                              "%d rejected as too similar." % rejected if rejected
                              else "None were duplicates."))
            else:
                st.warning("Everything built was too close to something existing.")

    for e in (st.session_state.get("last_generated") or [])[:3]:
        with card(key="card_generated_%s" % e["id"]):
            st.markdown("**%s** · %s · built from `%s` · %d attempt(s)"
                        % (e["id"], e["technique"], e["built_from"], e["attempts"]))
            st.markdown("**From:** `%s`" % e["sender_email"])
            if e.get("reply_to"):
                st.markdown("**Reply-To:** :red[`%s`]" % e["reply_to"])
            st.markdown("**Subject:** %s" % e["subject"])
            st.text_area("b", e["body"], height=170, disabled=True,
                         label_visibility="collapsed", key="gen_%s" % e["id"])
            x1, x2 = columns(key="generated_notes_%s" % e["id"], kind="controls")
            with x1:
                st.markdown("**Entities swapped**")
                for k, v in e["entities_used"].items():
                    st.markdown("- `%s` -> %s" % (k, v))
            with x2:
                st.markdown("**Modifications**")
                for m in e["modifications"]:
                    st.markdown("- `%s`" % m)

    generated_csv = service.generated_csv()
    if generated_csv is not None:
        st.download_button("Download generated_emails.csv", generated_csv,
                           file_name="generated_emails.csv", mime="text/csv")

    st.subheader("Email catalogue")
    st.caption(
        "The original emails and the shared generated-email pool used by experiments and practice. "
        "For a built email you can see exactly what was changed."
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
            "None built yet. Generate emails above, assign practice in **Person**, "
            "or use **Build new emails** in **Live** or **Run**."
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
        } for e in pool])

        st.caption("%d emails. Scroll or use table search to find a record." % len(pool))
        show_table(listing, height=350, visible=["id", "subject", "technique", "cue", "changes"], config={
            "id": st.column_config.TextColumn("ID"),
            "technique": st.column_config.TextColumn("Attack type"),
            "cue": st.column_config.TextColumn("Pressure"),
            "sender": st.column_config.TextColumn("Sender"),
            "subject": st.column_config.TextColumn("Subject"),
            "changes": st.column_config.TextColumn("Changes"),
        })

        # ---- one email in full ----
        ids = [e["id"] for e in pool]
        labels = {e["id"]: "%s - %s" % (e["id"], e.get("subject", "")[:54])
                  for e in pool}
        # A stable key, and labels that cannot collide: two emails can share
        # a subject, and without the id in the value the widget loses track
        # of which one was open whenever the pool grows.
        pick = st.selectbox("Open one", ids[::-1], key="open_email",
                            format_func=lambda i: labels.get(i, str(i)))
        chosen = next((e for e in pool if e["id"] == pick), None)

        if chosen:
            c1, c2 = columns(key="email_preview")

            with c1, card("Email preview", key="card_email_preview"):
                st.markdown("**From:** %s `<%s>`"
                            % (chosen.get("sender_name", "?"),
                               chosen.get("sender_email", "")))
                if chosen.get("reply_to"):
                    st.markdown("**Reply-To:** :red[`%s`]" % chosen["reply_to"])
                st.markdown("**Subject:** %s" % chosen.get("subject", ""))
                st.text_area("Body", chosen.get("body", ""), height=240,
                             disabled=True, label_visibility="collapsed",
                             key="emailtab_body_%s" % pick)

            with c2, card("Details and teaching notes", key="card_email_notes"):
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
                    st.markdown("**Before and after** - built from the genuine "
                                "email `%s`" % base["id"])
                    d1, d2 = columns(key="email_comparison")
                    with d1, card(key="card_email_original"):
                        st.markdown(":blue[**Genuine original**]")
                        st.markdown("**From:** `%s`" % base.get("sender_email", ""))
                        st.markdown("**Reply-To:** `%s`"
                                    % (base.get("reply_to") or "none"))
                        st.text_area("orig", base.get("body", ""), height=240,
                                     disabled=True, label_visibility="collapsed",
                                     key="emailtab_orig_%s" % pick)
                    with d2, card(key="card_email_modified"):
                        st.markdown(":red[**After the changes**]")
                        st.markdown("**From:** `%s`" % chosen.get("sender_email", ""))
                        st.markdown("**Reply-To:** `%s`"
                                    % (chosen.get("reply_to") or "none"))
                        st.text_area("made", chosen.get("body", ""), height=240,
                                     disabled=True, label_visibility="collapsed",
                                     key="emailtab_made_%s" % pick)

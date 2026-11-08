"""Small, shared layout primitives for ALERT's existing Streamlit views."""

from contextlib import contextmanager

import streamlit as st


def main_screens():
    """The two top-level routes; each keeps its own tools in the workspace."""
    with st.container(border=True, key="main_screens"):
        st.caption("Main screens")
        st.page_link("app.py", label="App", icon=":material/mail:", width="stretch")
        st.page_link("pages/admin.py", label="Admin", icon=":material/admin_panel_settings:", width="stretch")


def columns(count=2, *, key, kind="panels", vertical_alignment="top"):
    """Native columns inside a grid that measures its own available space.

    Panels, form controls and metrics have different readable minimum sizes.
    Keep the native column contexts so widget state and routing stay intact.
    """
    if kind not in ("panels", "controls", "metrics", "actions"):
        raise ValueError("Unknown grid kind")
    with st.container(key="grid_%s_%s" % (kind, key)):
        return st.columns(count, gap="small", vertical_alignment=vertical_alignment)


def page_header(title, description, area="Admin"):
    st.caption("ALERT / %s" % area)
    st.title(title)
    if description:
        st.caption(description)


@contextmanager
def card(title=None, description=None, key=None):
    with st.container(border=True, key=key):
        if title:
            st.subheader(title)
        if description:
            st.caption(description)
        yield

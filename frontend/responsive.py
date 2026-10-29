# frontend/responsive.py
# Makes the app usable in a narrow window and on a phone.
#
# Streamlit lays columns out with flexbox and, under layout="wide", keeps
# them side by side however narrow the window gets. A row of four metrics
# or a 3:2 split then squeezes to a few characters per column instead of
# stacking. There is no server-side way to know the window width, so the
# breakpoints are CSS - the browser decides, and the page reflows as it is
# resized rather than only at load.
#
# Columns are given a minimum readable width rather than a breakpoint that
# stacks them all at once. flex-wrap then does the arithmetic: as the window
# narrows, a row of four metrics becomes three, then two, then one, and each
# one stays wide enough to read. A single breakpoint would have left the
# tablet widths squeezed to about a hundred pixels per column.
#
#   > 1100px   unchanged, the layout the app was designed at
#   <= 1100px  tighter padding, columns wrap below 220px rather than shrink
#   <= 760px   one column per row, tabs scroll sideways, charts can be swiped
#
# Everything here is presentation. Nothing in it changes what the app does.

import streamlit as st

# Streamlit's own test ids. They are the documented hooks for styling, but
# they do belong to Streamlit, so a major upgrade is the thing that would
# break this file.
CSS = """
<style>
/* Let a row of columns wrap instead of squeezing past readability. */
[data-testid="stHorizontalBlock"] {
    flex-wrap: wrap;
}

@media (max-width: 1100px) {
    /* The wide layout reserves a lot of side padding. Give it back. */
    .block-container {
        padding-left: 2rem;
        padding-right: 2rem;
        padding-top: 3rem;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.5rem;
    }
    /* Wrap rather than squeeze. Streamlit's inline flex-basis still sets
       the share of a row; this only stops a column going below legible. */
    [data-testid="stColumn"] {
        min-width: 220px;
    }
}

@media (max-width: 760px) {
    .block-container {
        padding-left: 1rem;
        padding-right: 1rem;
        padding-top: 2.5rem;
    }

    /* One column per row. The inline flex-basis Streamlit writes has to be
       overridden, which is what needs the !important. */
    [data-testid="stColumn"] {
        min-width: 100% !important;
        flex: 1 1 100% !important;
    }

    /* Eight tabs do not fit on a phone. Swipe them instead of wrapping
       them into a block that pushes the content down. */
    [data-testid="stTabs"] [role="tablist"] {
        overflow-x: auto;
        flex-wrap: nowrap;
        scrollbar-width: thin;
    }
    [data-testid="stTab"] {
        flex: 0 0 auto;
        white-space: nowrap;
    }

    /* A chart has a minimum readable width. Below it, scroll rather than
       shrink the labels into illegibility. */
    [data-testid="stVegaLiteChart"], [data-testid="stDataFrame"] {
        overflow-x: auto;
    }

    [data-testid="stMetricValue"] {
        font-size: 1.35rem;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.8rem;
    }

    /* Full-width buttons in a stacked row are easier to hit than the
       centred narrow ones Streamlit leaves behind. */
    [data-testid="stColumn"] .stButton > button {
        width: 100%;
    }

    h1 { font-size: 1.6rem; }
    h2 { font-size: 1.3rem; }
    h3 { font-size: 1.1rem; }
}

/* Very narrow: hide the decorative header bar so the tabs sit higher. */
@media (max-width: 480px) {
    .block-container {
        padding-top: 2rem;
    }
    [data-testid="stMetricValue"] {
        font-size: 1.2rem;
    }
}
</style>
"""


def inject():
    """Add the responsive rules. Call once, right after set_page_config."""
    st.markdown(CSS, unsafe_allow_html=True)

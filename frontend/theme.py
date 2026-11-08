# theme.py
# How the app looks: the palette, the chart styling, and the wording used
# for a verdict.
#
# This is the frontend half of what used to sit in app.py. It is here so the
# colours are defined once - a chart, a metric and a badge showing the same
# thing should not each pick their own red.
#
# The palette was checked with the data-viz validator, light and dark:
#   clicked vs recognised -> the diverging poles, red against blue
#   awareness             -> one blue hue, three ordinal steps light to dark

import altair as alt

CLICKED = "#e34948"
RECOGNISED = "#2a78d6"
AWARENESS_SCALE = {"low": "#86b6ef", "medium": "#2a78d6", "high": "#104281"}
INK = "#0b0b0b"
MUTED = "#52514e"
GRID = "#e6e5e2"

AWARENESS_ORDER = ["low", "medium", "high"]


def readable_chart(chart):
    """One legible chart style; Streamlit supplies light/dark text colors."""
    return (chart.configure_view(strokeWidth=0)
            .configure_axis(labelFontSize=14, titleFontSize=14,
                            labelPadding=6, titlePadding=10, labelLimit=190,
                            gridOpacity=0.18, domainOpacity=0.25, tickOpacity=0.25)
            .configure_legend(labelFontSize=14, titleFontSize=14,
                              orient="top", columns=3, padding=8)
            .configure_header(labelFontSize=14, titleFontSize=14))


def chart_base(df):
    """Shared chart styling: recessive axes, no chart junk."""
    return readable_chart(alt.Chart(df))


def verdict_of(rec):
    """(label, streamlit colour) for one arrival.

    A false alarm is called out separately from a correct catch: reporting
    genuine mail is a different mistake from clicking a phish, and lumping
    them together hides which one a person actually makes.
    """
    if rec["label"] != "phishing":
        return ("FALSE ALARM", "orange") if rec["action"] == "report" \
            else ("genuine", "gray")
    if rec["action"] == "click":
        return "CLICKED", "red"
    if rec["action"] == "report":
        return "RECOGNISED", "blue"
    return "ignored", "gray"

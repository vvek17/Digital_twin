"""Presentation of the existing delivery-weighted awareness comparison."""

import json
import textwrap

import altair as alt
import pandas as pd

from frontend.theme import CLICKED, RECOGNISED, readable_chart


def recognition_data(workforce):
    """Same sums/denominators as Dashboard; labels and missing-data handling only."""
    columns = ["awareness", "seen", "response", "count", "rate"]
    if workforce.empty or "seen" not in workforce:
        return pd.DataFrame(columns=columns)
    frame = workforce.copy()
    for field in ("seen", "clicked", "reported"):
        frame[field] = pd.to_numeric(frame.get(field, pd.Series(index=frame.index, dtype=float)),
                                      errors="coerce").fillna(0)
    frame = frame[frame["seen"] > 0].copy()
    if frame.empty:
        return pd.DataFrame(columns=columns)
    if "awareness" not in frame:
        frame["awareness"] = "Unknown"
    frame["awareness"] = (frame["awareness"].fillna("Unknown").astype(str)
                          .str.strip().replace("", "Unknown").str.capitalize())
    grouped = frame.groupby("awareness", as_index=False)[["seen", "clicked", "reported"]].sum()
    data = grouped.melt(id_vars=["awareness", "seen"], value_vars=["clicked", "reported"],
                        var_name="response", value_name="count")
    data["response"] = data["response"].map({"clicked": "Clicked", "reported": "Recognised"})
    data["rate"] = data["count"] / data["seen"]
    return data[columns]


def awareness_order(data):
    present = data["awareness"].dropna().unique().tolist()
    standard = ["Low", "Medium", "High"]
    return [level for level in standard if level in present] + sorted(
        level for level in present if level not in standard)


def recognition_chart(data):
    """Grouped bars with a horizontal awareness axis and direct value labels."""
    levels = awareness_order(data)
    labels = {level: textwrap.wrap(level, 14, break_on_hyphens=False) for level in levels}
    base = alt.Chart(data).encode(
        x=alt.X("awareness:N", sort=levels, title=None,
                scale=alt.Scale(paddingInner=0.22, paddingOuter=0.12),
                axis=alt.Axis(labelAngle=0, labelOverlap=False, labelPadding=9,
                              labelLimit=135, labelExpr="(%s)[datum.label]" % json.dumps(labels))),
        xOffset=alt.XOffset("response:N", sort=["Clicked", "Recognised"],
                           scale=alt.Scale(paddingInner=0.1, paddingOuter=0.08)),
        y=alt.Y("rate:Q", title=None, scale=alt.Scale(domain=[0, 1], nice=False),
                axis=alt.Axis(format=".0%", values=[0, 0.2, 0.4, 0.6, 0.8, 1],
                              grid=True)),
        color=alt.Color("response:N", title=None,
                        scale=alt.Scale(domain=["Clicked", "Recognised"],
                                        range=[CLICKED, RECOGNISED]),
                        legend=alt.Legend(orient="top", direction="horizontal", columns=2,
                                          symbolType="square", symbolSize=90, offset=12)),
        tooltip=[alt.Tooltip("awareness:N", title="Awareness"),
                 alt.Tooltip("response:N", title="Response"),
                 alt.Tooltip("rate:Q", title="Percentage", format=".2%"),
                 alt.Tooltip("count:Q", title="Responses", format=",.0f"),
                 alt.Tooltip("seen:Q", title="Phishing delivered", format=",.0f")],
    )
    bars = base.mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
    # Let Streamlit's theme supply neutral, high-contrast text rather than
    # making small numeric labels depend on the bar colors.
    labels = alt.Chart(data).mark_text(dy=-8, fontSize=14, fontWeight=500,
                                     color="currentColor").encode(
        x=base.encoding.x, xOffset=base.encoding.xOffset, y=base.encoding.y,
        text=alt.Text("rate:Q", format=".0%"), tooltip=base.encoding.tooltip)
    chart = alt.layer(bars, labels).properties(height=280, padding={
        "top": 20, "bottom": 2, "left": 0, "right": 0})
    # Many future/custom levels can scroll horizontally instead of dropping
    # categories or shrinking labels. The normal three-level chart stretches.
    if len(levels) > 4:
        chart = chart.properties(width=alt.Step(110))
    return readable_chart(chart)

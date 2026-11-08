"""Row-based dashboard charts. Metrics arrive already calculated by the views."""

import json
import textwrap

import altair as alt

from frontend.theme import AWARENESS_SCALE, CLICKED, readable_chart


def row_axis(values, width=24):
    """Wrap labels without dropping names; tooltips retain their full values."""
    labels = {str(key): textwrap.wrap(str(value), width, break_long_words=True,
                                     break_on_hyphens=False) or ["Unknown"]
              for key, value in values}
    step = max(30, 16 * max((len(lines) for lines in labels.values()), default=1) + 12)
    return alt.Axis(labelExpr="(%s)[datum.label]" % json.dumps(labels),
                    labelOverlap=False, labelLimit=215, labelPadding=10,
                    ticks=False, domain=False), step


def staff_chart(ranked):
    frame = ranked.copy()
    # Stable person keys also keep two people with identical names on separate rows.
    frame["person_key"] = frame["id"].astype(str) if "id" in frame else frame.index.astype(str)
    frame["awareness"] = frame["awareness"].fillna("unknown")
    axis, step = row_axis(zip(frame["person_key"], frame["name"]))
    extra = sorted(set(frame["awareness"]) - set(AWARENESS_SCALE))
    levels = list(AWARENESS_SCALE) + extra
    colors = list(AWARENESS_SCALE.values()) + [
        "hsl(%.2f, 48%%, 38%%)" % ((280 + i * 137.508) % 360) for i in range(len(extra))]
    base = alt.Chart(frame).encode(
        x=alt.X("click_rate:Q", title=None, scale=alt.Scale(domain=[0, 1.16], nice=False),
                axis=alt.Axis(format=".0%", values=[0, .25, .5, .75, 1])),
        y=alt.Y("person_key:N", title=None, sort=frame["person_key"].tolist(), axis=axis),
        tooltip=[alt.Tooltip("name:N", title="Person"), alt.Tooltip("role:N", title="Role"),
                 alt.Tooltip("awareness:N", title="Awareness"),
                 alt.Tooltip("seen:Q", title="Phishing delivered"),
                 alt.Tooltip("clicked:Q", title="Clicked"),
                 alt.Tooltip("click_rate:Q", title="Clicked (%)", format=".2%")],
    )
    bars = base.mark_bar(cornerRadiusEnd=3, height=12).encode(
        color=alt.Color("awareness:N", title=None,
                        scale=alt.Scale(domain=levels, range=colors),
                        legend=alt.Legend(orient="top", labelLimit=100, columns=1,
                                          labelExpr="upper(slice(datum.label, 0, 1)) + slice(datum.label, 1)")))
    labels = base.mark_text(align="left", dx=6, color="currentColor", fontSize=14).encode(
        text=alt.Text("click_rate:Q", format=".0%"))
    return readable_chart((bars + labels).properties(height=alt.Step(step),
        autosize=alt.AutoSizeParams(type="fit-x", contains="padding")))


def pressure_chart(aggregate):
    axis, step = row_axis(zip(aggregate["display_type"], aggregate["display_type"]), width=22)
    base = alt.Chart(aggregate).encode(
        y=alt.Y("display_type:N", title=None, sort=aggregate["display_type"].tolist(), axis=axis),
        x=alt.X("rate:Q", title=None, axis=None, scale=alt.Scale(domain=[0, 1.23], nice=False)),
        tooltip=[alt.Tooltip("display_type:N", title="Category"),
                 alt.Tooltip("asked:Q", title="Phishing delivered"),
                 alt.Tooltip("fooled:Q", title="Trusted it"),
                 alt.Tooltip("rate:Q", title="Trusted (%)", format=".2%")])
    tracks = base.mark_bar(height=8, cornerRadius=4, color="currentColor", opacity=.09).encode(
        x=alt.X(datum=1, type="quantitative", axis=None,
                scale=alt.Scale(domain=[0, 1.23], nice=False)))
    bars = base.mark_bar(height=8, cornerRadius=4, color=CLICKED)
    values = base.mark_text(align="right", color="currentColor", fontSize=14).encode(
        x=alt.X(datum=1.22, type="quantitative", axis=None,
                scale=alt.Scale(domain=[0, 1.23], nice=False)),
        text=alt.Text("rate:Q", format=".0%"))
    return readable_chart((tracks + bars + values).properties(height=alt.Step(step),
        autosize=alt.AutoSizeParams(type="fit-x", contains="padding")))

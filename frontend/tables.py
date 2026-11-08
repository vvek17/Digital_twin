"""Shared table presentation for training and administration."""

import streamlit as st
import pandas as pd
from pandas.api.types import is_numeric_dtype, is_bool_dtype


def PCT_BAR(label, hi=100, color=None):
    """A percentage shown as a filled bar rather than a bare number."""
    return st.column_config.ProgressColumn(
        label, format="%.0f%%", min_value=0, max_value=hi, width=128, color=color)


def table_height(records, maximum=350):
    """Fit short tables to their rows; large tables use native virtualization."""
    return min(maximum, 40 + max(1, records) * 34)


def column_layout(frame, config=None, index=False):
    """Size tracks from display labels, observed values, and column semantics.

    This is independent of viewport size: the native grid clamps its natural
    content width to the parent and virtualizes/scrolls only when necessary.
    """
    configured = {name: dict(value) if isinstance(value, dict) else value
                  for name, value in (config or {}).items()}
    for name in frame.columns:
        column = configured.get(name)
        if column is None and name in configured:
            continue  # Explicitly hidden by the caller.
        column = dict(column or {})
        if column.get("width") is not None:
            continue
        raw_label = str(name).replace("_", " ")
        default_label = ((raw_label[:1].upper() + raw_label[1:])
                         .replace(" id", " ID").replace(" utc", " UTC"))
        if raw_label.lower() == "id":
            default_label = "ID"
        label = str(column.get("label") or default_label)
        column.setdefault("label", label)
        values = frame[name]
        sample = values.dropna().astype(str)
        lengths = sample.str.len()
        typical = int(lengths.quantile(.9, interpolation="lower")) if not lengths.empty else 0
        kind = column.get("type_config", {}).get("type")
        key = str(name).lower()
        if kind == "progress":
            width = 128
        else:
            if is_bool_dtype(values) or kind == "checkbox":
                minimum, maximum = 72, 140
            elif is_numeric_dtype(values) or kind == "number":
                minimum, maximum = 72, 148
            elif any(word in key for word in ("subject", "description", "detail", "error")):
                minimum, maximum = 180 if typical else 80, 340
            elif key == "person" and not sample.empty and sample.str.fullmatch(r"[A-Za-z]*\d+").all():
                minimum, maximum = 80, 112
            elif key in ("name", "person", "person_name", "role", "job_title", "file"):
                minimum, maximum = 165, 270
                typical = int(lengths.max()) if not lengths.empty else 0
            elif any(word in key for word in ("time", "date", "modified")):
                minimum, maximum = 120, 225
            else:
                minimum, maximum = 80, 220
            width = min(maximum, max(minimum, round(max(len(label), typical) * 7.6 + 28)))
        column["width"] = width
        configured[name] = column
    if index and "_index" not in configured:
        configured["_index"] = {"width": max(100, min(180, max(
            (len(str(value)) for value in frame.index), default=0) * 8 + 28))}
    return configured


def show_table(df, height=350, config=None, index=False, font_weight=None, visible=None):
    if len(df) == 0:
        st.info("No records to show. Add data or adjust the filters.")
        return None
    frame = df if isinstance(df, pd.DataFrame) else pd.DataFrame(df)
    styled = frame.style.set_properties(**{"font-weight": str(font_weight)}) if (
        font_weight is not None) else frame
    return st.dataframe(
        styled,
        width="content",
        hide_index=not index,
        height=table_height(len(frame), min(height, 380)),
        column_config=column_layout(frame, config, index),
        column_order=visible,
        row_height=34,
    )

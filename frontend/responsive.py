"""Shared readable typography, compact spacing, and responsive workspace layout.

Grids measure the workspace, including sidebar changes, rather than relying
on browser-width breakpoints. Native tables own their scrolling and controls.
"""

import streamlit as st

# Styling stays scoped to Streamlit test ids and our own container keys.
# Check these selectors when upgrading Streamlit's rendered components.
CSS = """
<style>
:root {
    --alert-space-1: 4px;
    --alert-space-2: 8px;
    --alert-space-3: 12px;
    --alert-space-4: 16px;
    --alert-space-5: 24px;
    --alert-radius: 12px;
}
/* A reading workspace, with native content-sized grids inside it. */
.block-container {
    max-width: 1340px; margin-inline: auto;
    padding: 3.5rem clamp(0.9rem, 2vw, 1.5rem) 2rem;
    min-width: 0; box-sizing: border-box;
}
[class*="st-key-grid_"] { min-width: 0; max-width: 100%; }
[class*="st-key-grid_"] > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] {
    display: grid; gap: var(--alert-space-4); align-items: start;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 24rem), 1fr));
}
[class*="st-key-grid_controls_"] > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] {
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 12rem), 1fr));
    align-items: end;
}
[class*="st-key-grid_metrics_"] > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] {
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 9rem), 1fr));
}
[class*="st-key-grid_actions_"] > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] {
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 8rem), 1fr));
}
[class*="st-key-grid_"] > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    min-width: 0; width: 100%; max-width: 100%; box-sizing: border-box;
}
/* Scroll the graphic, leaving its sibling native toolbar outside the clip. */
.st-key-staff_plot [data-testid="stVegaLiteChart"],
.st-key-pressure_plot [data-testid="stVegaLiteChart"] {
    max-block-size: min(60dvh, 38rem); overflow: auto; scrollbar-gutter: stable;
}
.st-key-staff_plot [data-testid="stFullScreenFrame"]:has(button[aria-label="Close fullscreen"]) [data-testid="stVegaLiteChart"],
.st-key-pressure_plot [data-testid="stFullScreenFrame"]:has(button[aria-label="Close fullscreen"]) [data-testid="stVegaLiteChart"] {
    max-block-size: none;
}
[data-testid="stVerticalBlock"] { gap: var(--alert-space-3); }
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li { font-size: 16px; line-height: 1.5; }
[data-testid="stMarkdownContainer"] { overflow-wrap: anywhere; }
[data-testid="stCaptionContainer"] p { font-size: 14px; line-height: 1.45; }
h1 { font-size: 28px !important; letter-spacing: -0.025em; padding-bottom: 0.35rem !important; }
h2 { font-size: 22px !important; letter-spacing: -0.015em; padding-bottom: 0.3rem !important; }
h3 { font-size: 20px !important; letter-spacing: -0.01em; padding-bottom: 0.25rem !important; }
button, input, textarea, [role="combobox"] { font-size: 16px !important; }
[data-testid="stTextArea"] textarea:disabled {
    color: inherit; -webkit-text-fill-color: currentColor; opacity: 1;
}
button { border-radius: 8px !important; }
[data-testid="stWidgetLabel"] p,
[data-testid="stMetricLabel"] p { font-size: 15px; }
[data-testid="stMetricValue"] p { font-size: 26px !important; font-weight: 600; }
[data-testid="stMetric"] {
    border: 1px solid color-mix(in srgb, currentColor 12%, transparent);
    border-radius: 10px; padding: 12px 14px;
    background: color-mix(in srgb, currentColor 2%, transparent);
}
/* Card boundaries follow content instead of setting artificial heights. */
[class*="st-key-card_"], .st-key-dashboard_clicks,
.st-key-dashboard_recognition, .st-key-dashboard_breakdown {
    border-radius: var(--alert-radius);
    box-shadow: 0 2px 10px rgb(0 0 0 / 4%);
    background: color-mix(in srgb, currentColor 1%, transparent);
}
[data-testid="stForm"], [data-testid="stExpander"] { border-radius: 10px; }
[data-testid="stDataFrame"] { border-radius: 9px; max-width: 100%; }
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p { font-size: 15px; }
[data-testid="stSidebar"] [role="radiogroup"] { gap: 3px; }
[data-testid="stSidebar"] [role="radiogroup"] > div { width: 100%; }
[data-testid="stSidebar"] [role="radiogroup"] label {
    padding: 7px 8px; border-radius: 8px; border-left: 2px solid transparent;
    width: 100%; box-sizing: border-box;
}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
    background: color-mix(in srgb, currentColor 6%, transparent);
    border-left-color: #2a78d6;
}
[data-testid="stColumn"] { min-width: 0; }
hr { margin: 0.5rem 0 !important; }
.st-key-dashboard_recognition [data-testid="stVegaLiteChart"] { overflow-x: auto; }
[data-testid="stVegaLiteChart"] { max-width: 100%; }

/* Email reader and source-backed answer review. */
.alert-mail, .alert-feedback { color: inherit; font-size: 16px; min-width: 0; }
.alert-mail { max-width: 100%; }
.alert-mail .alert-mail-subject {
    margin: 0 0 18px; padding: 0 !important; line-height: 1.35; overflow-wrap: anywhere;
}
.alert-mail-sender { display: flex; align-items: center; gap: 12px; margin-bottom: 10px; }
.alert-mail-sender > div { min-width: 0; }
.alert-mail-avatar {
    display: inline-flex; align-items: center; justify-content: center;
    flex: 0 0 40px; height: 40px; border-radius: 50%; font-weight: 600; font-size: 14px;
    background: color-mix(in srgb, #2a78d6 12%, transparent);
}
.alert-mail-name { font-weight: 600; margin-bottom: 3px; overflow-wrap: anywhere; }
.alert-mail-address, .alert-mail-detail { font-size: 14px; line-height: 1.6; overflow-wrap: anywhere; }
.alert-mail-address { font-family: ui-monospace, SFMono-Regular, Consolas, monospace; margin-bottom: 16px; }
.alert-mail-from { font-size: 14px; opacity: .7; margin-bottom: 3px; }
.alert-mail-detail { display: flex; flex-wrap: wrap; gap: 4px 12px; margin-bottom: 12px; }
.alert-mail-detail > span:first-child { font-weight: 600; }
.alert-mail-body {
    white-space: pre-wrap; overflow-wrap: anywhere; font-size: 16px; line-height: 1.65;
    padding-block: 18px; border-block: 1px solid color-mix(in srgb, currentColor 12%, transparent);
    max-block-size: min(62dvh, 40rem); overflow-y: auto; scrollbar-gutter: stable;
}
.alert-mail-body:focus-visible, .alert-mail-inspection summary:focus-visible {
    outline: 2px solid #2a78d6; outline-offset: 3px; border-radius: 4px;
}
.alert-mail-inspection { margin-top: 14px; font-size: 14px; }
.alert-mail-inspection summary { cursor: pointer; font-weight: 500; }
.alert-mail-inspection dl, .alert-feedback dl { margin: 10px 0 0; }
.alert-mail-inspection dt, .alert-feedback dt { font-size: 14px; opacity: .75; margin-bottom: 3px; }
.alert-mail-inspection dd, .alert-feedback dd { margin: 0 0 10px; overflow-wrap: anywhere; }
.alert-feedback-status {
    display: flex; align-items: center; gap: 10px; padding: 12px 14px; border-radius: 9px;
    --feedback-accent: #2a78d6;
    background: color-mix(in srgb, var(--feedback-accent) 10%, transparent);
    border: 1px solid color-mix(in srgb, var(--feedback-accent) 32%, transparent);
}
.alert-feedback-status--correct { --feedback-accent: #2a8560; }
.alert-feedback-status--incorrect { --feedback-accent: #ca4b4b; }
.alert-feedback-symbol { font-size: 20px; font-weight: 600; }
.alert-feedback-facts { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 160px), 1fr)); gap: 4px 14px; }
.alert-feedback-facts dd { font-weight: 600; }
.alert-feedback-explanation { margin: 4px 0 0; line-height: 1.6; }
.alert-feedback-section {
    margin-top: 18px; padding-top: 16px;
    border-top: 1px solid color-mix(in srgb, currentColor 12%, transparent);
}
.alert-feedback h4 { margin: 0 0 8px; font-size: 17px; font-weight: 600; line-height: 1.4; }
.alert-feedback p { margin: 0; line-height: 1.6; overflow-wrap: anywhere; }
.alert-feedback ul { margin: 0; padding-left: 20px; }
.alert-feedback li { margin: 7px 0; line-height: 1.6; overflow-wrap: anywhere; }
.alert-feedback-inspection { margin-top: 14px; padding: 12px; border-radius: 8px; background: color-mix(in srgb, currentColor 3%, transparent); }
.alert-feedback-inspection summary { cursor: pointer; font-size: 14px; font-weight: 500; }
.alert-feedback-inspection dd { font-size: 14px; }
.alert-feedback-takeaway { padding: 14px; border: 0; border-radius: 8px; background: color-mix(in srgb, #2a78d6 7%, transparent); }
.alert-feedback-muted { opacity: .7; }
.st-key-grid_metrics_inbox_progress > [data-testid="stLayoutWrapper"] > [data-testid="stHorizontalBlock"] {
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 5.5rem), 1fr)); gap: 8px;
}
.st-key-grid_metrics_inbox_progress [data-testid="stMetric"] { padding: 10px; }

@media (max-width: 760px) {
    .block-container { padding-bottom: 1.25rem; }
    [data-testid="stMetricValue"] p { font-size: 24px !important; }
}
</style>
"""


def inject():
    """Add the responsive rules. Call once, right after set_page_config."""
    st.markdown(CSS, unsafe_allow_html=True)

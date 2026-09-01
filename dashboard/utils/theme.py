"""Dashboard themes (dark/light): central palette, CSS generation and Plotly helpers.

The theme is resolved at render time from `st.session_state['theme_mode']`
(default 'dark'), so all pages pull their colors/CSS from here instead of hardcoding
them. `PALETTE` is kept as the dark palette for backward-compatibility with imports
that read it at module scope; runtime consumers should use `get_palette()`.
"""
from pathlib import Path

import streamlit as st

DARK_PALETTE = {
    "primary": "#4F46E5",
    "blue": "#2563EB",
    "green": "#16A34A",
    "red": "#DC2626",
    "orange": "#EA580C",
    "amber": "#F59E0B",
    "dark": "#111827",
    "light": "#F9FAFB",
    "text": "#F3F4F6",
    "text_muted": "#9AA3B2",
    "text_faint": "#6B7280",
    "card_bg": "#0F1524",
    "card_border": "rgba(255, 255, 255, 0.08)",
    "bg_page": "#0B1020",
    "bg_sidebar_b": "#131A2E",
    "grid": "rgba(255, 255, 255, 0.10)",
}

LIGHT_PALETTE = {
    "primary": "#4F46E5",
    "blue": "#1D4ED8",
    "green": "#15803D",
    "red": "#B91C1C",
    "orange": "#C2410C",
    "amber": "#B45309",
    "dark": "#111827",
    "light": "#FFFFFF",
    "text": "#1F2937",
    "text_muted": "#4B5563",
    "text_faint": "#6B7280",
    "card_bg": "#FFFFFF",
    "card_border": "rgba(15, 23, 42, 0.12)",
    "bg_page": "#F1F5F9",
    "bg_sidebar_b": "#D9E2F0",
    "grid": "rgba(15, 23, 42, 0.10)",
}

# Backward-compatible default (dark); prefer get_palette() at render time.
PALETTE = DARK_PALETTE

_BASE_CSS = """
<style>
:root {
  --pif-primary: @primary@;
  --pif-blue: @blue@;
  --pif-green: @green@;
  --pif-red: @red@;
  --pif-orange: @orange@;
  --pif-text: @text@;
  --pif-text-muted: @text_muted@;
  --pif-text-faint: @text_faint@;
  --pif-card-bg: @card_bg@;
  --pif-card-border: @card_border@;
  --pif-bg-page: @bg_page@;
  --pif-bg-sidebar-a: @bg_page@;
  --pif-bg-sidebar-b: @bg_sidebar_b@;
  --pif-grid: @grid@;
}

.stApp { background: var(--pif-bg-page) !important; color: var(--pif-text); }
.stApp header { background: transparent !important; }
.block-container { padding-top: 1.4rem; }
#MainMenu, footer { visibility: hidden; }

h1, h2, h3 { color: var(--pif-text); letter-spacing: -0.01em; }
a { color: var(--pif-blue); }

.pif-card {
  background: var(--pif-card-bg);
  border: 1px solid var(--pif-card-border);
  border-radius: 12px;
  padding: 14px 16px;
}
.pif-card-title { font-size: 0.95rem; font-weight: 600; color: var(--pif-text); }
.pif-card-desc { font-size: 0.78rem; color: var(--pif-text-muted); line-height: 1.45; }
.pif-section-sub { margin: -0.2rem 0 0.5rem 0; color: var(--pif-text-muted); font-size: 0.82rem; }

div[data-testid="stMetric"] {
  background: var(--pif-card-bg);
  border: 1px solid var(--pif-card-border);
  border-radius: 12px;
  padding: 12px 14px;
}
div[data-testid="stMetricValue"] { color: var(--pif-text); }

.stButton button, .stDownloadButton button, [data-testid="stFormSubmitButton"] button {
  border-radius: 8px;
  font-weight: 600;
}

div[data-baseweb="tab-list"] { gap: 6px; }
div[data-baseweb="tab"] { border-radius: 8px 8px 0 0; padding: 4px 14px; }
.stDataFrame { border: 1px solid var(--pif-card-border); border-radius: 10px; overflow: hidden; }
</style>
"""

# Extra overrides only injected when the dashboard is in light mode. Streamlit's
# native theme is statically dark (.streamlit/config.toml), so natively-dark
# widgets must be restyled explicitly or they would look broken on a light page.
_LIGHT_OVERRIDES = """
<style>
[data-testid="stSidebar"] { color: var(--pif-text); }
[data-testid="stSidebar"] .stMarkdown p { color: var(--pif-text); }
[data-testid="stSidebar"] .stMarkdown { color: var(--pif-text); }

div[data-baseweb="input"], div[data-baseweb="textarea"], [data-testid="stTextInput"] input,
[data-testid="stTextArea"] textarea, [data-testid="stNumberInput"] input {
  background: var(--pif-card-bg) !important;
  border-color: var(--pif-card-border) !important;
  color: var(--pif-text) !important;
}
div[data-baseweb="select"] > div { background: var(--pif-card-bg) !important; color: var(--pif-text); }

[data-testid="stExpander"] details {
  background: var(--pif-card-bg);
  border: 1px solid var(--pif-card-border);
  border-radius: 10px;
}
[data-testid="stExpander"] summary { color: var(--pif-text); }

[data-testid="stMultiSelect"] > div { background: var(--pif-card-bg) !important; color: var(--pif-text); }

.stButton button, .stDownloadButton button, [data-testid="stFormSubmitButton"] button {
  background: var(--pif-card-bg);
  color: var(--pif-text);
  border: 1px solid var(--pif-card-border);
}

[data-testid="stDataFrame"] { background: var(--pif-card-bg) !important; }
[data-testid="stDataFrame"] tbody td, [data-testid="stDataFrame"] thead th { color: var(--pif-text); }

.stAlert { background: var(--pif-card-bg); color: var(--pif-text); }

div[data-testid="stMetric"] { background: var(--pif-card-bg); }
div[data-testid="stMetricLabel"] p { color: var(--pif-text-muted); }

[data-testid="stCaptionContainer"] p, .stCaption { color: var(--pif-text-muted); }
</style>
"""


def get_theme_mode() -> str:
    return st.session_state.get("theme_mode", "dark")


def set_theme_mode(mode: str) -> None:
    st.session_state["theme_mode"] = mode if mode == "light" else "dark"


def get_palette(mode: str | None = None) -> dict:
    return LIGHT_PALETTE if (mode or get_theme_mode()) == "light" else DARK_PALETTE


def get_plotly_template(mode: str | None = None) -> str:
    return "plotly_white" if (mode or get_theme_mode()) == "light" else "plotly_dark"


def css_string(mode: str | None = None) -> str:
    mode = mode or get_theme_mode()
    p = get_palette(mode)
    css = _BASE_CSS + (_LIGHT_OVERRIDES if mode == "light" else "")
    for key, value in p.items():
        css = css.replace(f"@{key}@", str(value))
    return css


def inject_css(mode: str | None = None) -> None:
    st.markdown(css_string(mode), unsafe_allow_html=True)
    css = Path(__file__).resolve().parents[1] / "assets" / "css" / "custom.css"
    if css.exists():
        st.markdown(f"<style>{css.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)
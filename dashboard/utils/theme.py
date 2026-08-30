"""Dashboard color palette / theme helper."""
PALETTE = {
    "primary": "#4F46E5",
    "blue": "#2563EB",
    "green": "#16A34A",
    "red": "#DC2626",
    "orange": "#EA580C",
    "dark": "#111827",
    "light": "#F9FAFB",
}

CSS_GLOBAL = """
<style>
.stApp header { background: transparent !important; }
.block-container { padding-top: 1.2rem; }
#MainMenu, footer { visibility: hidden; }
div[data-testid="stMetricValue"] { font-size: 1.8rem; }
</style>
"""


def css_string() -> str:
    return CSS_GLOBAL
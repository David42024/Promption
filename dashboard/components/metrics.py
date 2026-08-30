"""Reusable metric cards with threshold-based colors."""
import streamlit as st

from dashboard.utils.theme import PALETTE

_CARD_BG = "#0F1524"
_CARD_BORDER = "1px solid rgba(255,255,255,0.08)"


def _card(html: str) -> None:
    st.markdown(
        f'<div style="background:{_CARD_BG};border:{_CARD_BORDER};border-radius:12px;'
        f'padding:14px 16px;margin-bottom:6px;height:100%;">{html}</div>',
        unsafe_allow_html=True,
    )


def pct(value: float, digits: int = 1) -> str:
    return f"{value * 100:.{digits}f}%"


def kpi_card(label: str, value: str, help_text: str = "", good_when="high", severity: float | None = None) -> None:
    """severity 0..1 drives the color. good_when: 'high' means higher is better."""
    if severity is None:
        color = PALETTE["primary"]
    else:
        if good_when == "high":
            if severity >= 0.8:
                color = PALETTE["green"]
            elif severity >= 0.5:
                color = PALETTE["orange"]
            else:
                color = PALETTE["red"]
        else:
            if severity <= 0.2:
                color = PALETTE["green"]
            elif severity <= 0.5:
                color = PALETTE["orange"]
            else:
                color = PALETTE["red"]
    _card(
        f'<div style="font-size:0.75rem;color:#9AA3B2;text-transform:uppercase;letter-spacing:0.06em;">{label}</div>'
        f'<div style="font-size:1.7rem;font-weight:700;color:{color};margin-top:2px;">{value}</div>'
        + (f'<div style="font-size:0.72rem;color:#6B7280;margin-top:4px;">{help_text}</div>' if help_text else "")
    )


def status_badge(text: str, ok: bool, ok_label: str = "OPERATIVO", bad_label: str = "NO DISPONIBLE") -> None:
    color = PALETTE["green"] if ok else PALETTE["red"]
    label = ok_label if ok else bad_label
    _card(f'<div style="font-size:0.78rem;color:#9AA3B2;">{text}</div>'
          f'<div style="font-size:1.1rem;font-weight:700;color:{color};">{label}</div>')


def trend_arrow(delta: float, good_when_down: bool = True) -> str:
    """delta>0 means value increased vs previous run."""
    improved = (delta < 0) if good_when_down else (delta > 0)
    arrow = "▼" if delta < 0 else "▲"
    color = PALETTE["green"] if improved else PALETTE["red"]
    return f'<span style="color:{color};font-weight:600;">{arrow} {abs(delta):.1f}%</span>'


def section_header(label: str) -> None:
    st.markdown(f'<h3 style="margin-top:0.4rem;color:#E5E7EB;">{label}</h3>', unsafe_allow_html=True)
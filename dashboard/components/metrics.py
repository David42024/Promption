"""Reusable metric cards with threshold-based colors."""
import streamlit as st

from dashboard.utils.theme import get_palette


def _card(html: str) -> None:
    pal = get_palette()
    st.markdown(
        f'<div class="pif-card" style="background:{pal["card_bg"]};'
        f'border:1px solid {pal["card_border"]};border-radius:12px;'
        f'padding:14px 16px;margin-bottom:6px;height:100%;">{html}</div>',
        unsafe_allow_html=True,
    )


def pct(value: float, digits: int = 1) -> str:
    return f"{value * 100:.{digits}f}%"


def _severity_color(good_when: str, severity: float) -> str:
    pal = get_palette()
    if good_when == "high":
        if severity >= 0.8:
            return pal["green"]
        if severity >= 0.5:
            return pal["orange"]
        return pal["red"]
    if severity <= 0.2:
        return pal["green"]
    if severity <= 0.5:
        return pal["orange"]
    return pal["red"]


def kpi_card(label: str, value: str, help_text: str = "",
             good_when="high", severity: float | None = None, icon: str | None = None) -> None:
    """severity 0..1 drives the color. good_when: 'high' means higher is better."""
    pal = get_palette()
    if severity is None:
        color = pal["primary"]
    else:
        color = _severity_color(good_when, severity)

    title = f'<span>{icon}</span><span>{label}</span>' if icon else label
    head = (f'<div style="display:flex;align-items:center;gap:6px;font-size:0.75rem;'
            f'color:{pal["text_muted"]};text-transform:uppercase;letter-spacing:0.06em;">{title}</div>')
    _card(
        head
        + f'<div style="font-size:1.7rem;font-weight:700;color:{color};margin-top:2px;">{value}</div>'
        + (f'<div style="font-size:0.72rem;color:{pal["text_faint"]};margin-top:4px;">{help_text}</div>'
           if help_text else "")
    )


def info_card(icon: str, title: str, description: str) -> None:
    """Generic content card (icon + title + description) sharing the KPI card style."""
    _card(
        f'<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">'
        f'<span style="font-size:1.4rem;line-height:1;">{icon}</span>'
        f'<span class="pif-card-title">{title}</span></div>'
        f'<div class="pif-card-desc">{description}</div>'
    )


def status_badge(text: str, ok: bool, ok_label: str = "OPERATIVO", bad_label: str = "NO DISPONIBLE") -> None:
    pal = get_palette()
    color = pal["green"] if ok else pal["red"]
    label = ok_label if ok else bad_label
    _card(f'<div style="font-size:0.78rem;color:{pal["text_muted"]};">{text}</div>'
          f'<div style="font-size:1.1rem;font-weight:700;color:{color};">{label}</div>')


def trend_arrow(delta: float, good_when_down: bool = True) -> str:
    """delta>0 means value increased vs previous run."""
    pal = get_palette()
    improved = (delta < 0) if good_when_down else (delta > 0)
    arrow = "▼" if delta < 0 else "▲"
    color = pal["green"] if improved else pal["red"]
    return f'<span style="color:{color};font-weight:600;">{arrow} {abs(delta):.1f}%</span>'


def section_header(label: str, subtitle: str | None = None) -> None:
    pal = get_palette()
    html = f'<h3 style="margin-top:0.7rem;color:{pal["text"]};">{label}</h3>'
    if subtitle:
        html += f'<div class="pif-section-sub">{subtitle}</div>'
    st.markdown(html, unsafe_allow_html=True)
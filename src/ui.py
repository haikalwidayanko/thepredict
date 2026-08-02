"""Shared presentation helpers: logo, per-section accent colours, page headers.

Each section gets a distinct accent so the two halves of the app read as
different worlds -- green for tennis (court), amber for crypto (markets) --
while sharing one layout language so it still feels like one product.
All palettes are tuned for the light theme in `.streamlit/config.toml`.
"""
from __future__ import annotations

from pathlib import Path

import streamlit as st

ASSETS = Path(__file__).resolve().parent.parent / "assets"
LOGO = ASSETS / "logo.svg"
ICON = ASSETS / "icon.svg"

SECTIONS = {
    "tennis": {
        "accent": "#15803d",       # green-700
        "accent_soft": "#f0fdf4",  # green-50
        "border": "#bbf7d0",       # green-200
        "eyebrow": "PREDIKSI OLAHRAGA",
    },
    "crypto": {
        "accent": "#b45309",       # amber-700
        "accent_soft": "#fffbeb",  # amber-50
        "border": "#fde68a",       # amber-200
        "eyebrow": "PASAR DERIVATIF",
    },
    "home": {
        "accent": "#0f766e",       # teal-700
        "accent_soft": "#f0fdfa",
        "border": "#99f6e4",
        "eyebrow": "",
    },
}


def show_logo() -> None:
    """Put the wordmark in the sidebar, above the page navigation."""
    if LOGO.exists():
        try:
            st.logo(str(LOGO), icon_image=str(ICON) if ICON.exists() else None)
        except Exception:
            pass  # older Streamlit without st.logo -- not worth failing over


def _css(section: str) -> str:
    s = SECTIONS[section]
    return f"""
    <style>
      /* Section accent -- retint the primary controls per page */
      .stTabs [aria-selected="true"] {{
          color: {s['accent']} !important;
      }}
      .stTabs [data-baseweb="tab-highlight"] {{
          background-color: {s['accent']} !important;
      }}
      /* Page header band */
      .app-header {{
          background: {s['accent_soft']};
          border: 1px solid {s['border']};
          border-left: 5px solid {s['accent']};
          border-radius: 10px;
          padding: 1.1rem 1.3rem;
          margin-bottom: 1.4rem;
      }}
      .app-header .eyebrow {{
          color: {s['accent']};
          font-size: 0.72rem;
          font-weight: 700;
          letter-spacing: 0.14em;
          text-transform: uppercase;
          margin: 0 0 0.35rem 0;
      }}
      .app-header h1 {{
          font-size: 1.75rem;
          font-weight: 700;
          color: #0f172a;
          margin: 0 0 0.3rem 0;
          line-height: 1.2;
      }}
      .app-header p {{
          color: #475569;
          font-size: 0.94rem;
          margin: 0;
      }}

      /* Cards for matches / coins */
      div[data-testid="stVerticalBlockBorderWrapper"] {{
          border-radius: 10px;
      }}

      /* Match kick-off line -- plain text so nothing gets truncated,
         unlike st.metric which clips long values to one line. */
      .match-schedule {{
          display: flex;
          flex-wrap: wrap;
          align-items: center;
          gap: 0.6rem 1.1rem;
          margin: 0.2rem 0 1rem 0;
      }}
      .match-schedule .time {{
          font-size: 1.35rem;
          font-weight: 700;
          color: {s['accent']};
          white-space: nowrap;
      }}
      .match-schedule .status {{
          font-size: 0.95rem;
          font-weight: 600;
          color: #334155;
          background: {s['accent_soft']};
          border: 1px solid {s['border']};
          border-radius: 999px;
          padding: 0.25rem 0.75rem;
      }}

      /* Metric values wrap instead of being clipped with an ellipsis. */
      div[data-testid="stMetricValue"] {{
          white-space: normal;
          overflow-wrap: anywhere;
          line-height: 1.25;
      }}
    </style>
    """


def page_header(section: str, title: str, subtitle: str = "") -> None:
    """Render the accent band at the top of a page."""
    s = SECTIONS[section]
    st.markdown(_css(section), unsafe_allow_html=True)
    eyebrow = f"<p class='eyebrow'>{s['eyebrow']}</p>" if s["eyebrow"] else ""
    sub = f"<p>{subtitle}</p>" if subtitle else ""
    st.markdown(
        f"<div class='app-header'>{eyebrow}<h1>{title}</h1>{sub}</div>",
        unsafe_allow_html=True,
    )


def accuracy_row(total: int, correct: int, hit_rate: float | None,
                 brier: float | None = None, noun: str = "prediksi") -> None:
    """The stats strip shown above a history table."""
    cols = st.columns(4 if brier is not None else 3)
    cols[0].metric(f"Total {noun}", total)
    cols[1].metric("Tepat", correct)
    cols[2].metric("Akurasi", f"{hit_rate*100:.0f}%" if hit_rate is not None else "—")
    if brier is not None:
        cols[3].metric(
            "Brier score",
            f"{brier:.3f}",
            help="Makin kecil makin baik (0 = sempurna, 0.25 = setara tebak acak)",
        )

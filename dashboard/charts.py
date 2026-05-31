"""Plotly chart helpers for the German Job Market Analytics dashboard."""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

# ── Palette ───────────────────────────────────────────────────────────────────
_BG = "#111111"
_GRID = "#242424"
_TEXT = "#e8e8e8"
_MUTED = "#888888"
_AXIS = "#9a9a9a"
_ACCENT = "#00d4ff"
_FONT_MONO = "'IBM Plex Mono', 'Courier New', monospace"
_FONT_SANS = "'IBM Plex Sans', 'Helvetica Neue', Arial, sans-serif"

_SKILL_COLORS: list[str] = [
    "#00d4ff", "#7ecba1", "#f5a623", "#e056c1",
    "#74b9ff", "#fd79a8", "#fdcb6e", "#55efc4",
    "#a29bfe", "#ff7675",
]

_ROLE_COLORS: list[str] = [
    _ACCENT, "#aaaaaa", "#777777", "#555555", "#444444", "#383838",
]

_SOURCE_COLORS: dict[str, str] = {
    "bundesagentur": "#00d4ff",
    "stepstone": "#aaaaaa",
    "linkedin": "#666666",
    "indeed": "#444444",
}

_LANG_COLORS: dict[str, str] = {
    "de": "#00d4ff",
    "en": "#888888",
    "unknown": "#444444",
}


def _apply_theme(fig: go.Figure, title: str, height: int = 480) -> go.Figure:
    """Apply the shared dark editorial theme to a figure in-place."""
    fig.update_layout(
        paper_bgcolor=_BG,
        plot_bgcolor=_BG,
        font=dict(family=_FONT_SANS, color=_TEXT, size=13),
        title=dict(
            text=title,
            font=dict(family=_FONT_SANS, color=_TEXT, size=15),
            pad=dict(l=4, b=10),
        ),
        height=height,
        margin=dict(l=16, r=16, t=52, b=16),
        legend=dict(
            bgcolor="rgba(0,0,0,0)",
            borderwidth=0,
            font=dict(family=_FONT_MONO, color=_MUTED, size=12),
        ),
        hoverlabel=dict(
            bgcolor="#1e1e1e",
            font_color=_TEXT,
            font_family=_FONT_MONO,
            font_size=13,
            bordercolor=_GRID,
        ),
    )
    fig.update_xaxes(
        gridcolor=_GRID,
        linecolor=_GRID,
        zerolinecolor=_GRID,
        tickfont=dict(family=_FONT_MONO, color=_AXIS, size=13),
        title_font=dict(family=_FONT_MONO, color=_AXIS, size=13),
    )
    fig.update_yaxes(
        gridcolor=_GRID,
        linecolor=_GRID,
        zerolinecolor=_GRID,
        tickfont=dict(family=_FONT_MONO, color=_AXIS, size=13),
        title_font=dict(family=_FONT_MONO, color=_AXIS, size=13),
    )
    return fig


def _empty_fig(title: str, message: str, height: int = 432) -> go.Figure:
    """Return a blank dark figure with a centred no-data message."""
    fig = go.Figure()
    fig.add_annotation(
        text=message,
        x=0.5, y=0.5,
        xref="paper", yref="paper",
        showarrow=False,
        font=dict(family=_FONT_SANS, color=_MUTED, size=14),
    )
    _apply_theme(fig, title, height)
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False)
    return fig


# ── Chart functions ───────────────────────────────────────────────────────────

def skill_trend_chart(df: pd.DataFrame) -> go.Figure:
    """Line chart — weekly demand for the top 10 skills.

    Parameters
    ----------
    df:
        Columns: skill (str), week_start (date-like), job_count (int).
    """
    if df.empty:
        return _empty_fig("Skill Demand Over Time", "No skill data — run the pipeline first")

    top_skills = (
        df.groupby("skill")["job_count"].sum()
        .nlargest(10)
        .index.tolist()
    )
    df_top = df[df["skill"].isin(top_skills)].copy()
    df_top["week_start"] = pd.to_datetime(df_top["week_start"])

    fig = go.Figure()
    for i, skill in enumerate(top_skills):
        sdf = df_top[df_top["skill"] == skill].sort_values("week_start")
        color = _SKILL_COLORS[i % len(_SKILL_COLORS)]
        is_accent = i == 0
        fig.add_trace(go.Scatter(
            x=sdf["week_start"],
            y=sdf["job_count"],
            mode="lines",
            name=skill,
            line=dict(color=color, width=3 if is_accent else 1.5),
            opacity=1.0 if is_accent else 0.8,
            hovertemplate=f"<b>{skill}</b><br>%{{x|%d %b %Y}}<br>%{{y}} jobs<extra></extra>",
        ))

    _apply_theme(fig, "Skill Demand Over Time", height=480)
    fig.update_layout(
        yaxis_title="Job postings",
        legend=dict(orientation="v", x=1.02, y=1, font=dict(size=12)),
        hovermode="x unified",
    )
    return fig


def role_by_city_chart(df: pd.DataFrame) -> go.Figure:
    """Horizontal stacked bar — job count per city, segmented by role category.

    Parameters
    ----------
    df:
        Columns: role_category (str), city (str), job_count (int).
    """
    if df.empty:
        return _empty_fig("Role Count by City", "No city data available")

    top_cities = (
        df.groupby("city")["job_count"].sum()
        .nlargest(15)
        .sort_values(ascending=True)  # ascending → highest count at chart top
        .index.tolist()
    )
    df_top = df[df["city"].isin(top_cities)]

    sorted_roles = (
        df_top.groupby("role_category")["job_count"].sum()
        .sort_values(ascending=False)
        .index.tolist()
    )

    fig = go.Figure()
    for i, role in enumerate(sorted_roles):
        rdf = df_top[df_top["role_category"] == role].set_index("city").reindex(top_cities).fillna(0)
        color = _ROLE_COLORS[i % len(_ROLE_COLORS)]
        fig.add_trace(go.Bar(
            y=top_cities,
            x=rdf["job_count"].values,
            name=role,
            orientation="h",
            marker_color=color,
            marker_line_width=0,
            hovertemplate=f"<b>{role}</b><br>%{{y}}<br>%{{x:.0f}} jobs<extra></extra>",
        ))

    height = int(max(384, len(top_cities) * 36 + 120))
    _apply_theme(fig, "Role Count by City", height=height)
    fig.update_layout(
        barmode="stack",
        xaxis_title="Job postings",
        legend=dict(
            orientation="h",
            x=0, y=-0.15,
            font=dict(size=12),
        ),
        margin=dict(l=16, r=16, t=52, b=72),
    )
    fig.update_xaxes(showgrid=True)
    fig.update_yaxes(showgrid=False)
    fig.add_hline(y=0, line_color=_GRID, line_width=1)
    return fig


def role_donut_chart(df: pd.DataFrame) -> go.Figure:
    """Donut chart — total job count by role category, aggregated across all cities.

    Parameters
    ----------
    df:
        Columns: role_category (str), city (str), job_count (int).
        The city dimension is collapsed; this is a summary view of role_by_city data.
    """
    if df.empty:
        return _empty_fig("Role Category Distribution", "No role data available")

    role_totals = (
        df.groupby("role_category")["job_count"]
        .sum()
        .sort_values(ascending=False)
        .reset_index()
    )
    n = len(role_totals)
    colors = [_ROLE_COLORS[i % len(_ROLE_COLORS)] for i in range(n)]

    fig = go.Figure()
    fig.add_trace(go.Pie(
        labels=role_totals["role_category"],
        values=role_totals["job_count"],
        hole=0.58,
        marker=dict(
            colors=colors,
            line=dict(color=_BG, width=3),
        ),
        textinfo="percent",
        textposition="inside",
        insidetextorientation="radial",
        textfont=dict(family=_FONT_MONO, color=_TEXT, size=13),
        hovertemplate="<b>%{label}</b><br>%{value:,} jobs<br>%{percent}<extra></extra>",
        direction="clockwise",
        sort=False,
    ))

    _apply_theme(fig, "Role Category Distribution", height=480)
    fig.update_layout(
        showlegend=True,
        legend=dict(
            orientation="v",
            x=1.0, y=0.5,
            xanchor="left",
            yanchor="middle",
            font=dict(family=_FONT_MONO, color=_MUTED, size=12),
        ),
        margin=dict(l=16, r=140, t=52, b=16),
    )
    return fig


def source_coverage_chart(df: pd.DataFrame) -> go.Figure:
    """Stacked bar chart — canonical record count per source per snapshot date.

    Parameters
    ----------
    df:
        Columns: source (str), snapshot_date (date-like), job_count (int).
    """
    if df.empty:
        return _empty_fig("Source Coverage by Date", "No coverage data available")

    df = df.copy()
    df["snapshot_date"] = pd.to_datetime(df["snapshot_date"])

    fig = go.Figure()
    for source in sorted(df["source"].unique()):
        sdf = df[df["source"] == source].sort_values("snapshot_date")
        color = _SOURCE_COLORS.get(source, _MUTED)
        fig.add_trace(go.Bar(
            x=sdf["snapshot_date"],
            y=sdf["job_count"],
            name=source,
            marker_color=color,
            marker_line_width=0,
            hovertemplate=f"<b>{source}</b><br>%{{x|%Y-%m-%d}}<br>%{{y}} jobs<extra></extra>",
        ))

    _apply_theme(fig, "Source Coverage by Snapshot Date", height=408)
    fig.update_layout(
        barmode="stack",
        yaxis_title="Job postings",
        legend=dict(orientation="h", x=0, y=-0.18, font=dict(size=12)),
        margin=dict(l=16, r=16, t=52, b=72),
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=True)
    fig.add_hline(y=0, line_color=_GRID, line_width=1)
    return fig


def language_ratio_chart(df: pd.DataFrame) -> go.Figure:
    """Stacked bar chart — language share per source (as percentages).

    Parameters
    ----------
    df:
        Columns: source (str), language (str), job_count (int), pct (float).
    """
    if df.empty:
        return _empty_fig("Language Ratio by Source", "No language data available")

    sources = sorted(df["source"].unique())
    languages = sorted(df["language"].unique())

    fig = go.Figure()
    for lang in languages:
        ldf = df[df["language"] == lang].set_index("source").reindex(sources).fillna(0)
        color = _LANG_COLORS.get(lang, _MUTED)
        fig.add_trace(go.Bar(
            x=sources,
            y=(ldf["pct"].values * 100),
            name=lang,
            marker_color=color,
            marker_line_width=0,
            hovertemplate=f"<b>{lang}</b><br>%{{x}}<br>%{{y:.1f}}%<extra></extra>",
        ))

    _apply_theme(fig, "Language Ratio by Source", height=408)
    fig.update_layout(
        barmode="stack",
        yaxis_title="Share (%)",
        legend=dict(orientation="h", x=0, y=-0.18, font=dict(size=12)),
        margin=dict(l=16, r=16, t=52, b=72),
    )
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=True, range=[0, 105], ticksuffix="%")
    fig.add_hline(y=0, line_color=_GRID, line_width=1)
    return fig

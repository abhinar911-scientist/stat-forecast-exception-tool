"""Plotly figures for the exception dashboard."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

import data as D

SURFACE = "#ffffff"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
GRID = "#e8e7e3"

SERIES_CURRENT = "#2a78d6"
SERIES_LAG1 = "#eb6834"

FONT = dict(family="Inter, Segoe UI, system-ui, sans-serif", size=13,
            color=INK_PRIMARY)


def _base_layout(fig: go.Figure, height: int, title: str | None = None) -> go.Figure:
    fig.update_layout(
        height=height,
        title=dict(text=title, font=dict(size=16, color=INK_PRIMARY), x=0, xanchor="left") if title else None,
        font=FONT,
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        margin=dict(l=8, r=16, t=48 if title else 16, b=8),
        hoverlabel=dict(bgcolor="white", bordercolor=GRID,
                        font=dict(family=FONT["family"], size=12)),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left",
                    x=0, font=dict(size=12, color=INK_SECONDARY),
                    title_text="", traceorder="normal"),
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=GRID,
                     ticks="outside", tickcolor=GRID,
                     tickfont=dict(color=INK_SECONDARY, size=12))
    fig.update_yaxes(showgrid=True, gridcolor=GRID, zeroline=False,
                     linecolor="rgba(0,0,0,0)",
                     tickfont=dict(color=INK_SECONDARY, size=12))
    return fig


def forecast_trend(trend: pd.DataFrame) -> go.Figure:
    """Current statistical forecast vs last month's committed, by month."""
    fig = go.Figure()
    if trend.empty:
        return _base_layout(fig, 360)

    months = trend[D.COL_MONTH]
    fig.add_trace(go.Scatter(
        x=months, y=trend[D.COL_STF], name="Statistical Forecast (current)",
        mode="lines+markers",
        line=dict(color=SERIES_CURRENT, width=2),
        marker=dict(size=8, color=SERIES_CURRENT,
                    line=dict(width=2, color=SURFACE)),
        hovertemplate="<b>%{x|%b %Y}</b><br>Current: %{y:,.0f} kg<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=months, y=trend[D.COL_STF_L1], name="Committed Lag 1",
        mode="lines+markers",
        line=dict(color=SERIES_LAG1, width=2),
        marker=dict(size=8, color=SERIES_LAG1,
                    line=dict(width=2, color=SURFACE)),
        hovertemplate="<b>%{x|%b %Y}</b><br>Committed Lag 1: %{y:,.0f} kg<extra></extra>",
    ))
    fig.update_layout(hovermode="x unified")
    fig.update_xaxes(dtick="M1", tickformat="%b %y")
    fig.update_yaxes(title_text="kg", title_font=dict(size=12, color=INK_SECONDARY),
                     tickformat=",.0f")
    return _base_layout(fig, 380)


def material_change_bars(mix: pd.DataFrame, order: list[str],
                         shorten_labels: bool = True) -> go.Figure:
    """Horizontal stacked bars: kg of forecast change per material, by category."""
    fig = go.Figure()
    if mix.empty or not order:
        return _base_layout(fig, 400)

    # Plotly draws the first y entry at the bottom, so reverse for a top-down rank.
    plot_order = list(reversed(order))
    labels = {m: (D.short_name(m) if shorten_labels else m) for m in plot_order}
    pivot = (mix.pivot_table(index=D.COL_MATERIAL, columns=D.COL_CATEGORY,
                             values=D.COL_DELTA, aggfunc="sum", observed=False)
                .reindex(plot_order).fillna(0.0))

    for cat in D.CATEGORY_ORDER:
        if cat not in pivot.columns or pivot[cat].sum() == 0:
            continue
        fig.add_trace(go.Bar(
            y=[labels[m] for m in plot_order],
            x=pivot[cat].values,
            name=cat,
            orientation="h",
            marker=dict(color=D.CATEGORY_COLORS[cat],
                        line=dict(width=2, color=SURFACE)),
            hovertemplate="<b>%{y}</b><br>" + cat + ": %{x:,.0f} kg<extra></extra>",
        ))

    totals = pivot.sum(axis=1)
    fig.add_trace(go.Scatter(
        y=[labels[m] for m in plot_order], x=totals.values,
        mode="text",
        text=[f"{v:,.0f}" for v in totals.values],
        textposition="middle right",
        textfont=dict(size=11, color=INK_SECONDARY),
        showlegend=False, hoverinfo="skip",
    ))

    height = max(420, 26 * len(plot_order) + 120)
    fig.update_layout(barmode="stack", bargap=0.3)
    fig.update_xaxes(title_text="Absolute forecast change (kg)",
                     title_font=dict(size=12, color=INK_SECONDARY),
                     showgrid=True, gridcolor=GRID, tickformat=",.0f",
                     range=[0, float(totals.max()) * 1.18 if totals.max() else 1])
    fig.update_yaxes(showgrid=False, automargin=True, tickfont=dict(size=11))
    return _base_layout(fig, height)

"""Plotly exhibits for the dashboard.

House style: one accent colour carrying the message, everything structural in
grey, no chart junk, direct labels instead of a hunt between legend and line.
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

import data as D

SURFACE = "#ffffff"
INK = "#10151c"
INK_SOFT = "#5a6472"
RULE = "#c9ced6"
GRID = "#eceef1"

CURRENT = "#1c5a92"     # this month's statistical forecast
PRIOR = "#9aa3ae"       # last month's committed — a reference line, kept grey

FONT = dict(family="Inter, Segoe UI, system-ui, sans-serif", size=13, color=INK)


def _frame(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(
        height=height,
        font=FONT,
        paper_bgcolor=SURFACE,
        plot_bgcolor=SURFACE,
        margin=dict(l=8, r=16, t=26, b=8),
        hoverlabel=dict(bgcolor="white", bordercolor=RULE,
                        font=dict(family=FONT["family"], size=12)),
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="left",
                    x=0, font=dict(size=11.5, color=INK_SOFT),
                    title_text="", traceorder="normal"),
    )
    fig.update_xaxes(showgrid=False, zeroline=False, linecolor=RULE,
                     ticks="outside", tickcolor=RULE, ticklen=4,
                     tickfont=dict(color=INK_SOFT, size=11.5))
    fig.update_yaxes(showgrid=True, gridcolor=GRID, zeroline=False,
                     linecolor="rgba(0,0,0,0)",
                     tickfont=dict(color=INK_SOFT, size=11.5))
    return fig


def forecast_trend(trend: pd.DataFrame) -> go.Figure:
    """Current statistical forecast against last month's committed, by month."""
    fig = go.Figure()
    if trend.empty:
        return _frame(fig, 360)

    months = trend[D.COL_MONTH]
    fig.add_trace(go.Scatter(
        x=months, y=trend[D.COL_STF_L1], name="Committed Lag 1",
        mode="lines+markers",
        line=dict(color=PRIOR, width=2, dash="dash"),
        marker=dict(size=7, color=PRIOR, line=dict(width=2, color=SURFACE)),
        hovertemplate="Committed Lag 1: %{y:,.0f} kg<extra></extra>",
    ))
    fig.add_trace(go.Scatter(
        x=months, y=trend[D.COL_STF], name="Statistical Forecast",
        mode="lines+markers",
        line=dict(color=CURRENT, width=2.5),
        marker=dict(size=8, color=CURRENT, line=dict(width=2, color=SURFACE)),
        hovertemplate="Statistical Forecast: %{y:,.0f} kg<extra></extra>",
    ))

    # Direct labels at the right edge so identity never depends on the legend.
    last = months.iloc[-1]
    for value, label, colour, shift in (
        (trend[D.COL_STF].iloc[-1], "Statistical Forecast", CURRENT, -12),
        (trend[D.COL_STF_L1].iloc[-1], "Committed Lag 1", PRIOR, 12),
    ):
        fig.add_annotation(x=last, y=value, text=label, showarrow=False,
                           xanchor="left", xshift=10, yshift=shift,
                           font=dict(size=11.5, color=colour))

    fig.update_layout(hovermode="x unified", showlegend=False)
    pad = pd.Timedelta(days=12)
    fig.update_xaxes(dtick="M1", tickformat="%b<br>%y",
                     range=[months.min() - pad, months.max() + pad])
    fig.update_yaxes(title_text="kg", title_font=dict(size=11.5, color=INK_SOFT),
                     tickformat=",.0f")
    fig.update_layout(margin=dict(l=8, r=160, t=26, b=8))
    return _frame(fig, 380)


def material_change_bars(mix: pd.DataFrame, order: list[str]) -> go.Figure:
    """Stacked bars: kg of forecast change per material, split by category."""
    fig = go.Figure()
    if mix.empty or not order:
        return _frame(fig, 400)

    # Plotly draws the first y entry at the bottom; reverse for a top-down rank.
    plot_order = list(reversed(order))
    labels = {m: D.short_name(m) for m in plot_order}
    pivot = (mix.pivot_table(index=D.COL_MATERIAL, columns=D.COL_CATEGORY,
                             values=D.COL_DELTA, aggfunc="sum", observed=False)
                .reindex(plot_order).fillna(0.0))

    for cat in D.CATEGORY_ORDER:
        if cat not in pivot.columns or pivot[cat].sum() == 0:
            continue
        fig.add_trace(go.Bar(
            y=[labels[m] for m in plot_order], x=pivot[cat].values,
            name=cat, orientation="h",
            marker=dict(color=D.CATEGORY_COLORS[cat],
                        line=dict(width=2, color=SURFACE)),
            hovertemplate="<b>%{y}</b><br>" + cat + ": %{x:,.0f} kg<extra></extra>",
        ))

    totals = pivot.sum(axis=1)
    fig.add_trace(go.Scatter(
        y=[labels[m] for m in plot_order], x=totals.values, mode="text",
        text=[f"{v:,.0f}" for v in totals.values],
        textposition="middle right",
        textfont=dict(size=11, color=INK_SOFT),
        showlegend=False, hoverinfo="skip",
    ))

    fig.update_layout(barmode="stack", bargap=0.34)
    fig.update_xaxes(title_text="Absolute change vs Lag 1 (kg)",
                     title_font=dict(size=11.5, color=INK_SOFT),
                     showgrid=True, gridcolor=GRID, tickformat=",.0f",
                     range=[0, float(totals.max()) * 1.2 if totals.max() else 1])
    fig.update_yaxes(showgrid=False, automargin=True,
                     tickfont=dict(size=11, color=INK))
    return _frame(fig, max(430, 26 * len(plot_order) + 120))

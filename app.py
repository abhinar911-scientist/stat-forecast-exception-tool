"""Statistical Forecast Exception List — Streamlit dashboard.

Input: the Arkieva "Statistical Forecast Exception list" export (M+1 .. M+13).
Purpose: surface the largest month-over-month changes in the statistical
forecast for activated (no-touch) material / ship-to combinations, so the
review process in step 02 starts from the exceptions that matter.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

import auth
import charts
import data as D

st.set_page_config(
    page_title="Statistical Forecast Exception List",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
  .block-container {padding-top: 2.2rem; padding-bottom: 3rem;}
  [data-testid="stMetricValue"] {font-size: 1.45rem;}
  [data-testid="stMetricLabel"] {color: #52514e;}
  h1 {font-size: 1.7rem !important; letter-spacing: -0.01em;}
  h3 {font-size: 1.1rem !important; margin-top: 0.4rem;}
  .stCaption, .caption {color: #52514e;}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

TOP_N = 30

FILTER_SPECS = [
    (D.COL_BL, "Business Line"),
    (D.COL_PL, "Product Line"),
    (D.COL_MATERIAL, "Material"),
    (D.COL_REGION, "Ship To Sub Region"),
    (D.COL_REVIEW, "Arkieva Review Req"),
    (D.COL_ABC, "Arkieva ABC"),
    (D.COL_VAR, "Arkieva Variability"),
    (D.COL_STATUS, "Arkieva Active Status"),
    (D.COL_PARENT, "Parent Customer"),
]


# ----------------------------------------------------------------- data -----

@st.cache_data(show_spinner="Reading the Arkieva report…", max_entries=3)
def _load(file_bytes: bytes, _name: str) -> pd.DataFrame:
    return D.load_dataframe(file_bytes)


def _fmt_filter_value(value):
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return D.short_name(value) if st.session_state.get("short_names", True) else value


def _month_label(ts) -> str:
    return pd.Timestamp(ts).strftime("%b %Y")


# -------------------------------------------------------------- sidebar -----

def sidebar_controls(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    st.sidebar.header("Filters")

    if st.sidebar.button("Reset all filters", use_container_width=True):
        for col, _ in FILTER_SPECS:
            st.session_state.pop(f"flt_{col}", None)
        st.session_state.pop("horizon", None)
        st.rerun()

    selections: dict = {}
    for col, _ in FILTER_SPECS:
        selections[col] = st.session_state.get(f"flt_{col}", [])

    for col, label in FILTER_SPECS:
        others = {c: v for c, v in selections.items() if c != col}
        options = D.options_for(D.apply_filters(df, others), col)
        key = f"flt_{col}"
        # Drop any previously picked value that the other filters ruled out.
        kept = [v for v in st.session_state.get(key, []) if v in options]
        st.session_state[key] = kept
        chosen = st.sidebar.multiselect(
            label, options, key=key, format_func=_fmt_filter_value,
            placeholder="All",
        )
        selections[col] = chosen

    st.sidebar.divider()
    st.sidebar.toggle("Short names (strip codes)", value=True, key="short_names")
    st.sidebar.toggle(
        "Ignore moves between unclassified codes", value=True,
        key="merge_placeholders",
        help="Arkieva writes '-' and 'Unknown' for combinations it has not "
             "classified. With this on, a move between those codes is not "
             "counted as a segmentation change.",
    )

    return D.apply_filters(df, selections), selections


# ----------------------------------------------------------------- views ----

def horizon_slider(df: pd.DataFrame):
    months = D.month_options(df)
    if not months:
        return None, None, []
    labels = [_month_label(m) for m in months]
    lookup = dict(zip(labels, months))
    if len(labels) == 1:
        st.caption(f"Horizon: {labels[0]} (single month in file)")
        return months[0], months[0], months
    start_label, end_label = st.select_slider(
        "Forecast horizon",
        options=labels,
        value=st.session_state.get("horizon", (labels[0], labels[-1])),
        key="horizon",
        help="Drag either handle to narrow the months. Every table and chart "
             "below respects this selection.",
    )
    start, end = lookup[start_label], lookup[end_label]
    if start > end:
        start, end = end, start
    return start, end, months


def kpi_row(scoped: pd.DataFrame) -> None:
    k = D.kpis(scoped)
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Statistical Forecast", f"{k['stat_forecast']:,.0f} kg")
    c2.metric("Committed Lag 1", f"{k['lag1_forecast']:,.0f} kg")
    c3.metric("Net change", f"{k['net_delta']:,.0f} kg")
    pct = k["abs_delta_pct"]
    c4.metric("Absolute change", f"{k['abs_delta']:,.0f} kg",
              help="Sum of |current − lag 1| across every row in scope.")
    c5.metric("Combinations changed",
              f"{k['combos_changed']:,} / {k['combos']:,}",
              delta=f"{(pct * 100):.1f}% abs vs lag 1" if pd.notna(pct) else None,
              delta_color="off")


def _table_config(group_cols: list[str]) -> dict:
    cfg = {
        D.COL_STF: st.column_config.NumberColumn("Stat Forecast (kg)", format="%,.0f"),
        D.COL_STF_L1: st.column_config.NumberColumn("Committed Lag 1 (kg)", format="%,.0f"),
        D.COL_DELTA: st.column_config.NumberColumn("Abs Delta vs Lag 1 (kg)", format="%,.0f"),
        D.COL_DELTA_PCT: st.column_config.NumberColumn("Delta % vs Lag 1", format="percent"),
    }
    for c in group_cols:
        cfg[c] = st.column_config.TextColumn(c)
    return cfg


def exception_table_block(scoped: pd.DataFrame, group_cols: list[str],
                          title: str, caption: str, key: str) -> None:
    st.markdown(f"### {title}")
    st.caption(caption)
    table = D.exception_table(scoped, group_cols, TOP_N)
    if table.empty:
        st.info("Nothing changed versus lag 1 in the current scope — no exceptions to review.")
        return
    st.caption(
        f"Showing {len(table)} of {D.changed_group_count(scoped, group_cols):,} "
        "combinations whose forecast moved."
    )
    display = D.shorten(table, group_cols) if st.session_state.get("short_names", True) else table
    st.dataframe(display, use_container_width=True, hide_index=True,
                 column_config=_table_config(group_cols), height=min(640, 38 * len(display) + 40))
    st.download_button(
        "Download this table (CSV)",
        table.to_csv(index=False).encode("utf-8"),
        file_name=f"{key}.csv", mime="text/csv", key=f"dl_{key}",
    )


def category_legend() -> None:
    st.caption(
        "Categories compare this month's Arkieva segmentation with last month's: "
        "**Pattern Change** = Arkieva Pattern moved · **Status Change** = Arkieva "
        "Active Status moved · **Status and Pattern Change** = both moved · "
        "**No Change** = segmentation identical, so the forecast movement comes "
        "from history and model refit alone."
    )


# ------------------------------------------------------------------ main ----

def dashboard() -> None:
    st.sidebar.markdown("## Statistical Forecast\n### Exception List")
    auth.logout_button()
    st.sidebar.divider()

    uploaded = st.sidebar.file_uploader(
        "Arkieva export (.xlsx)", type=["xlsx", "xlsm"],
        help="The Statistical Forecast Exception list input data extract, "
             "covering M+1 to M+13.",
    )

    st.title("Statistical Forecast Exception List")

    if uploaded is None:
        st.info(
            "Upload the Arkieva **Statistical Forecast Exception list** export in the "
            "sidebar to begin. The file must contain these columns:\n\n"
            + ", ".join(f"`{c}`" for c in D.REQUIRED_COLUMNS)
        )
        st.stop()

    try:
        df = _load(uploaded.getvalue(), uploaded.name)
    except D.DataError as exc:
        st.error(str(exc))
        st.stop()

    months = D.month_options(df)
    st.caption(
        f"**{uploaded.name}** · {len(df):,} rows · horizon "
        f"{_month_label(months[0])} – {_month_label(months[-1])} · "
        f"{df[D.COL_MATERIAL].nunique():,} materials"
    )

    filtered, _ = sidebar_controls(df)

    if not st.session_state.get("merge_placeholders", True):
        filtered = filtered.copy()
        filtered[D.COL_CATEGORY] = D.categorise(filtered, merge_placeholders=False)

    if filtered.empty:
        st.warning("No data matches the current filter selection. Reset a filter in the sidebar.")
        st.stop()

    start, end, _ = horizon_slider(filtered)
    scoped = D.filter_months(filtered, start, end)

    if scoped.empty:
        st.warning("No data in the selected month range.")
        st.stop()

    st.divider()
    kpi_row(scoped)
    st.divider()

    tab_tables, tab_trend, tab_mix = st.tabs(
        ["Top exceptions", "Forecast trend", "Change by material"]
    )

    with tab_tables:
        exception_table_block(
            scoped,
            [D.COL_BL, D.COL_PL, D.COL_MATERIAL, D.COL_REGION],
            f"Top {TOP_N} changes — Material × Ship To Sub Region",
            "Aggregated over the selected horizon and ranked by absolute kg change "
            "(volume weighted), largest first.",
            "top_exceptions_material_region",
        )
        st.divider()
        exception_table_block(
            scoped,
            [D.COL_BL, D.COL_PL, D.COL_MATERIAL, D.COL_REGION, D.COL_PARENT],
            f"Top {TOP_N} changes — with Parent Customer",
            "Same ranking, broken down to the parent customer that drives the change.",
            "top_exceptions_with_parent_customer",
        )

    with tab_trend:
        st.markdown("### Forecast by month")
        trend = D.monthly_trend(scoped)
        st.plotly_chart(charts.forecast_trend(trend), use_container_width=True,
                        config={"displayModeBar": False})
        with st.expander("Show the monthly numbers"):
            table = trend.copy()
            table[D.COL_MONTH] = table[D.COL_MONTH].dt.strftime("%b %Y")
            table["Delta (kg)"] = table[D.COL_STF] - table[D.COL_STF_L1]
            st.dataframe(table, use_container_width=True, hide_index=True)

    with tab_mix:
        st.markdown(f"### Top {TOP_N} materials by volume of forecast change")
        category_legend()
        mix, order = D.material_change_mix(scoped, TOP_N)
        if not order:
            st.info("No forecast movement in the current scope.")
        else:
            if set(mix[D.COL_CATEGORY].unique()) == {D.CAT_NO_CHANGE}:
                st.info(
                    "Every material in scope kept its Arkieva pattern and active "
                    "status this cycle, so all movement here is model refit on new "
                    "history rather than re-segmentation."
                )
            st.plotly_chart(
                charts.material_change_bars(
                    mix, order, st.session_state.get("short_names", True)),
                use_container_width=True, config={"displayModeBar": False},
            )
            with st.expander("Show the underlying numbers"):
                wide = (mix.pivot_table(index=D.COL_MATERIAL, columns=D.COL_CATEGORY,
                                        values=D.COL_DELTA, aggfunc="sum", observed=False)
                           .reindex(order).fillna(0.0).reset_index())
                wide["Total (kg)"] = wide.drop(columns=[D.COL_MATERIAL]).sum(axis=1)
                st.dataframe(wide, use_container_width=True, hide_index=True)


def main() -> None:
    if not auth.login_gate():
        return
    dashboard()


if __name__ == "__main__":
    main()

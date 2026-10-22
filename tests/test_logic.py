"""Unit tests for the metric and filter logic (no Streamlit runtime needed)."""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import numpy as np
import pandas as pd
import pytest

import data as D


def _row(**kw):
    base = {
        D.COL_BL: "Cleaning__BL02", D.COL_PL: "PF Alk__PF1",
        D.COL_PARENT: "CUST A__1", D.COL_SHIPTO: "Ship A__1",
        D.COL_REGION: "Europe", D.COL_MATERIAL: "MAT A__1",
        D.COL_ABC: "A", D.COL_VAR: "L",
        D.COL_STATUS: "Active", D.COL_STATUS_L1: "Active",
        D.COL_PATTERN: "Stable", D.COL_PATTERN_L1: "Stable",
        D.COL_REVIEW: True, D.COL_REVIEW_L1: True,
        D.COL_MONTH: pd.Timestamp("2026-11-01"),
        D.COL_STF: 100.0, D.COL_STF_L1: 80.0,
    }
    base.update(kw)
    return base


def frame(rows):
    return D.prepare(pd.DataFrame(rows))


def test_delta_and_category_basics():
    df = frame([_row()])
    assert df[D.COL_DELTA].iloc[0] == 20.0
    assert df[D.COL_SIGNED].iloc[0] == 20.0
    assert df[D.COL_CATEGORY].iloc[0] == D.CAT_NO_CHANGE


def test_delta_is_absolute_for_decreases():
    df = frame([_row(**{D.COL_STF: 50.0, D.COL_STF_L1: 80.0})])
    assert df[D.COL_DELTA].iloc[0] == 30.0
    assert df[D.COL_SIGNED].iloc[0] == -30.0


@pytest.mark.parametrize("pat,pat1,sta,sta1,expected", [
    ("Stable", "Stable", "Active", "Active", D.CAT_NO_CHANGE),
    ("Stable", "Erratic", "Active", "Active", D.CAT_PATTERN),
    ("Stable", "Stable", "Active", "Sparse", D.CAT_STATUS),
    ("Stable", "Erratic", "Active", "Sparse", D.CAT_BOTH),
])
def test_categorisation(pat, pat1, sta, sta1, expected):
    df = frame([_row(**{D.COL_PATTERN: pat, D.COL_PATTERN_L1: pat1,
                        D.COL_STATUS: sta, D.COL_STATUS_L1: sta1})])
    assert df[D.COL_CATEGORY].iloc[0] == expected


def test_delta_pct_formula_and_zero_denominator():
    rows = [
        _row(**{D.COL_MATERIAL: "M1__1", D.COL_STF: 150.0, D.COL_STF_L1: 100.0}),
        _row(**{D.COL_MATERIAL: "M2__2", D.COL_STF: 10.0, D.COL_STF_L1: 0.0}),
    ]
    out = D.exception_table(frame(rows), [D.COL_MATERIAL], 10).set_index(D.COL_MATERIAL)
    assert out.loc["M1__1", D.COL_DELTA] == 50.0
    assert out.loc["M1__1", D.COL_DELTA_PCT] == pytest.approx(0.5)
    assert np.isnan(out.loc["M2__2", D.COL_DELTA_PCT])


def test_aggregation_happens_before_delta():
    """Offsetting months must net out at the aggregate, not double-count."""
    rows = [
        _row(**{D.COL_MONTH: pd.Timestamp("2026-11-01"), D.COL_STF: 100.0, D.COL_STF_L1: 50.0}),
        _row(**{D.COL_MONTH: pd.Timestamp("2026-12-01"), D.COL_STF: 50.0, D.COL_STF_L1: 100.0}),
    ]
    out = D.exception_table(frame(rows), [D.COL_MATERIAL], 10, only_changed=False)
    assert out[D.COL_STF].iloc[0] == 150.0
    assert out[D.COL_STF_L1].iloc[0] == 150.0
    assert out[D.COL_DELTA].iloc[0] == 0.0
    # and it is not an exception, so the default view drops it
    assert D.exception_table(frame(rows), [D.COL_MATERIAL], 10).empty


def test_top_n_is_ranked_by_kg_not_percent():
    rows = [
        _row(**{D.COL_MATERIAL: "BIG__1", D.COL_STF: 10_000.0, D.COL_STF_L1: 9_000.0}),
        _row(**{D.COL_MATERIAL: "SMALL__2", D.COL_STF: 10.0, D.COL_STF_L1: 1.0}),
    ]
    out = D.exception_table(frame(rows), [D.COL_MATERIAL], 1)
    assert len(out) == 1
    assert out[D.COL_MATERIAL].iloc[0] == "BIG__1"


def test_month_filter_is_inclusive_both_ends():
    rows = [_row(**{D.COL_MONTH: pd.Timestamp(m)}) for m in
            ("2026-11-01", "2026-12-01", "2027-01-01")]
    df = frame(rows)
    got = D.filter_months(df, pd.Timestamp("2026-11-01"), pd.Timestamp("2026-12-01"))
    assert len(got) == 2


def test_filters_cascade_and_empty_means_all():
    rows = [_row(), _row(**{D.COL_BL: "Personal Care__BL03", D.COL_REGION: "North America"})]
    df = frame(rows)
    assert len(D.apply_filters(df, {D.COL_BL: []})) == 2
    assert len(D.apply_filters(df, {D.COL_BL: ["Cleaning__BL02"]})) == 1
    narrowed = D.apply_filters(df, {D.COL_BL: ["Cleaning__BL02"]})
    assert D.options_for(narrowed, D.COL_REGION) == ["Europe"]


def test_missing_column_raises_data_error():
    bad = pd.DataFrame([_row()]).drop(columns=[D.COL_STF_L1])
    with pytest.raises(D.DataError, match="missing these required columns"):
        D.prepare(bad)


def test_null_lag_values_are_zero_filled():
    df = frame([_row(**{D.COL_STF_L1: np.nan})])
    assert df[D.COL_STF_L1].iloc[0] == 0.0
    assert df[D.COL_DELTA].iloc[0] == 100.0


def test_material_mix_orders_by_total_change_and_splits_by_category():
    rows = [
        _row(**{D.COL_MATERIAL: "A__1", D.COL_STF: 300.0, D.COL_STF_L1: 0.0}),
        _row(**{D.COL_MATERIAL: "B__2", D.COL_STF: 100.0, D.COL_STF_L1: 0.0,
                D.COL_PATTERN: "Stable", D.COL_PATTERN_L1: "Erratic"}),
        _row(**{D.COL_MATERIAL: "C__3", D.COL_STF: 0.0, D.COL_STF_L1: 0.0}),
    ]
    mix, order = D.material_change_mix(frame(rows), 30)
    assert order == ["A__1", "B__2"]          # zero-change material excluded
    cats = dict(zip(mix[D.COL_MATERIAL], mix[D.COL_CATEGORY]))
    assert cats["A__1"] == D.CAT_NO_CHANGE
    assert cats["B__2"] == D.CAT_PATTERN


def test_whitespace_and_bool_coercion():
    raw = pd.DataFrame([_row(**{D.COL_PATTERN: " Stable ", D.COL_REVIEW: "TRUE"})])
    df = D.prepare(raw)
    assert df[D.COL_PATTERN].iloc[0] == "Stable"
    assert df[D.COL_REVIEW].iloc[0] is np.True_ or df[D.COL_REVIEW].iloc[0] == True


def test_short_name():
    assert D.short_name("Cleaning__BL02") == "Cleaning"
    assert D.short_name("Europe") == "Europe"


def test_monthly_trend_sums_per_month():
    rows = [
        _row(**{D.COL_MONTH: pd.Timestamp("2026-11-01"), D.COL_STF: 10.0, D.COL_STF_L1: 5.0}),
        _row(**{D.COL_MONTH: pd.Timestamp("2026-11-01"), D.COL_STF: 20.0, D.COL_STF_L1: 5.0,
                D.COL_MATERIAL: "X__9"}),
        _row(**{D.COL_MONTH: pd.Timestamp("2026-12-01"), D.COL_STF: 7.0, D.COL_STF_L1: 1.0}),
    ]
    t = D.monthly_trend(frame(rows))
    assert list(t[D.COL_STF]) == [30.0, 7.0]
    assert list(t[D.COL_STF_L1]) == [10.0, 1.0]


def test_empty_scope_returns_empty_structures():
    df = frame([_row()]).head(0)
    assert D.exception_table(df, [D.COL_MATERIAL]).empty
    assert D.monthly_trend(df).empty
    mix, order = D.material_change_mix(df)
    assert mix.empty and order == []


def test_placeholder_moves_are_not_a_change_by_default():
    df = frame([_row(**{D.COL_STATUS: "-", D.COL_STATUS_L1: "Unknown",
                        D.COL_PATTERN: "-", D.COL_PATTERN_L1: "Unknown"})])
    assert df[D.COL_CATEGORY].iloc[0] == D.CAT_NO_CHANGE
    strict = D.categorise(df, merge_placeholders=False)
    assert strict.iloc[0] == D.CAT_BOTH


def test_real_status_move_to_placeholder_still_counts():
    df = frame([_row(**{D.COL_STATUS: "-", D.COL_STATUS_L1: "Active"})])
    assert df[D.COL_CATEGORY].iloc[0] == D.CAT_STATUS


def test_loader_accepts_path_and_bytes(tmp_path):
    src = pd.DataFrame([_row()])
    f = tmp_path / "x.xlsx"
    src.to_excel(f, index=False)
    assert len(D.load_dataframe(str(f))) == 1
    assert len(D.load_dataframe(f.read_bytes())) == 1


def test_loader_rejects_a_non_arkieva_workbook(tmp_path):
    f = tmp_path / "bad.xlsx"
    pd.DataFrame({"a": [1], "b": [2]}).to_excel(f, index=False)
    with pytest.raises(D.DataError):
        D.load_dataframe(str(f))


def test_zero_change_rows_are_excluded_from_the_exception_table():
    rows = [
        _row(**{D.COL_MATERIAL: "MOVED__1", D.COL_STF: 120.0, D.COL_STF_L1: 100.0}),
        _row(**{D.COL_MATERIAL: "FLAT__2", D.COL_STF: 500.0, D.COL_STF_L1: 500.0}),
    ]
    df = frame(rows)
    out = D.exception_table(df, [D.COL_MATERIAL], 30)
    assert list(out[D.COL_MATERIAL]) == ["MOVED__1"]
    assert len(D.exception_table(df, [D.COL_MATERIAL], 30, only_changed=False)) == 2
    assert D.changed_group_count(df, [D.COL_MATERIAL]) == 1

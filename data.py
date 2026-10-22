"""Data loading, validation and metric logic for the Statistical Forecast Exception tool."""
from __future__ import annotations

import io
import pathlib

import pandas as pd
import numpy as np

# ---------------------------------------------------------------- schema ----

COL_BL = "Business Line"
COL_PL = "Product Line"
COL_PARENT = "Parent Cust"
COL_SHIPTO = "Ship To"
COL_REGION = "Ship To Sub Region"
COL_MATERIAL = "Material"
COL_ABC = "Arkieva ABC"
COL_VAR = "Arkieva Variability"
COL_STATUS = "Arkieva Active Status"
COL_STATUS_L1 = "Arkieva Active Status Lag 1"
COL_PATTERN = "Arkieva Pattern"
COL_PATTERN_L1 = "Arkieva Pattern Lag 1"
COL_REVIEW = "Arkieva Review Req"
COL_REVIEW_L1 = "Arkieva Review Req Lag 1"
COL_MONTH = "Month"
COL_STF = "Statistical Forecast (kg)"
COL_STF_L1 = "Statistical Forecast Committed Lag 1 (kg)"

REQUIRED_COLUMNS = [
    COL_BL, COL_PL, COL_PARENT, COL_SHIPTO, COL_REGION, COL_MATERIAL,
    COL_ABC, COL_VAR, COL_STATUS, COL_STATUS_L1, COL_PATTERN, COL_PATTERN_L1,
    COL_REVIEW, COL_REVIEW_L1, COL_MONTH, COL_STF, COL_STF_L1,
]

# Derived columns
COL_DELTA = "Absolute Delta vs Lag 1 (kg)"
COL_DELTA_PCT = "Delta % vs Lag 1"
COL_SIGNED = "Signed Delta vs Lag 1 (kg)"
COL_CATEGORY = "Segmentation Change Category"

FILTER_COLUMNS = [COL_BL, COL_PL, COL_MATERIAL, COL_REGION, COL_REVIEW,
                  COL_ABC, COL_VAR, COL_STATUS, COL_PARENT]

# Arkieva writes several tokens that all mean "not classified". Treating a move
# between them as a segmentation change would flood the chart with false flags.
PLACEHOLDERS = {"-", "", "unknown", "n/a", "na", "none", "nan", "not classified"}
UNCLASSIFIED = "Unclassified"

CAT_NO_CHANGE = "No Change"
CAT_PATTERN = "Pattern Change"
CAT_STATUS = "Status Change"
CAT_BOTH = "Status and Pattern Change"
CATEGORY_ORDER = [CAT_NO_CHANGE, CAT_PATTERN, CAT_STATUS, CAT_BOTH]
CATEGORY_COLORS = {
    CAT_NO_CHANGE: "#1F4E99",   # deep blue
    CAT_PATTERN: "#1F9E6E",     # green
    CAT_STATUS: "#7B3F9E",      # purple
    CAT_BOTH: "#3FBFAE",        # teal
}


class DataError(Exception):
    """Raised when the uploaded workbook cannot be used."""


# ------------------------------------------------------------- loading ------

def _clean_text(series: pd.Series) -> pd.Series:
    out = series.astype("object").where(series.notna(), None)
    out = pd.Series([v.strip() if isinstance(v, str) else v for v in out],
                    index=series.index, dtype="object")
    return out.fillna("-").replace({"": "-"}).astype(str)


def _coerce_bool(series: pd.Series) -> pd.Series:
    if series.dtype == bool:
        return series
    mapping = {"true": True, "false": False, "yes": True, "no": False,
               "y": True, "n": False, "1": True, "0": False, "x": True}
    return (series.astype(str).str.strip().str.lower().map(mapping)
            .fillna(False).astype(bool))


def load_dataframe(source) -> pd.DataFrame:
    """Read the Arkieva export (path, bytes or file-like) into a tidy frame.

    calamine is several times faster than openpyxl on a 130k-row export; it is
    optional, so fall back cleanly when it is not installed.
    """
    raw = source.read() if hasattr(source, "read") else source
    if isinstance(raw, (str, pathlib.Path)):
        payload = pathlib.Path(raw).read_bytes()
    else:
        payload = bytes(raw)

    last_error: Exception | None = None
    for engine in ("calamine", "openpyxl"):
        try:
            df = pd.read_excel(io.BytesIO(payload), engine=engine)
            return prepare(df)
        except ImportError as exc:
            last_error = exc
            continue
        except DataError:
            raise
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue
    raise DataError(f"Could not read the workbook: {last_error}")


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Validate, clean and enrich a raw Arkieva frame."""
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise DataError(
            "The uploaded file is missing these required columns: "
            + ", ".join(missing)
        )
    df = df[REQUIRED_COLUMNS]

    if df.empty:
        raise DataError("The uploaded file contains no data rows.")

    text_cols = [COL_BL, COL_PL, COL_PARENT, COL_SHIPTO, COL_REGION,
                 COL_MATERIAL, COL_ABC, COL_VAR, COL_STATUS, COL_STATUS_L1,
                 COL_PATTERN, COL_PATTERN_L1]
    for c in text_cols:
        df[c] = _clean_text(df[c])

    for c in (COL_REVIEW, COL_REVIEW_L1):
        df[c] = _coerce_bool(df[c])

    df[COL_MONTH] = pd.to_datetime(df[COL_MONTH], errors="coerce")
    if df[COL_MONTH].isna().all():
        raise DataError("The 'Month' column could not be parsed as dates.")
    df = df[df[COL_MONTH].notna()].copy()
    # normalise to first of month
    df[COL_MONTH] = df[COL_MONTH].values.astype("datetime64[M]")

    for c in (COL_STF, COL_STF_L1):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    df[COL_SIGNED] = df[COL_STF] - df[COL_STF_L1]
    df[COL_DELTA] = df[COL_SIGNED].abs()
    df[COL_CATEGORY] = categorise(df)

    return df.reset_index(drop=True)


def _normalise_segment(series: pd.Series) -> pd.Series:
    lowered = series.astype(str).str.strip().str.lower()
    return series.where(~lowered.isin(PLACEHOLDERS), UNCLASSIFIED)


def categorise(df: pd.DataFrame, merge_placeholders: bool = True) -> pd.Series:
    """Classify each row by how its Arkieva segmentation moved vs last month.

    With ``merge_placeholders`` (the default) a move between Arkieva's
    not-classified tokens ('-', 'Unknown', blank) is not counted as a change.
    """
    if merge_placeholders:
        pattern = _normalise_segment(df[COL_PATTERN])
        pattern_l1 = _normalise_segment(df[COL_PATTERN_L1])
        status = _normalise_segment(df[COL_STATUS])
        status_l1 = _normalise_segment(df[COL_STATUS_L1])
    else:
        pattern, pattern_l1 = df[COL_PATTERN], df[COL_PATTERN_L1]
        status, status_l1 = df[COL_STATUS], df[COL_STATUS_L1]

    pattern_changed = pattern.ne(pattern_l1)
    status_changed = status.ne(status_l1)
    cat = np.select(
        [pattern_changed & status_changed, status_changed, pattern_changed],
        [CAT_BOTH, CAT_STATUS, CAT_PATTERN],
        default=CAT_NO_CHANGE,
    )
    return pd.Series(pd.Categorical(cat, categories=CATEGORY_ORDER),
                     index=df.index)


# ------------------------------------------------------------ filtering -----

def month_options(df: pd.DataFrame) -> list[pd.Timestamp]:
    return sorted(pd.to_datetime(df[COL_MONTH].unique()))


def apply_filters(df: pd.DataFrame, selections: dict) -> pd.DataFrame:
    """Apply value selections; an empty/absent selection means 'all'."""
    out = df
    for col, values in selections.items():
        if col not in out.columns:
            continue
        if values is None or len(values) == 0:
            continue
        out = out[out[col].isin(list(values))]
    return out


def filter_months(df: pd.DataFrame, start, end) -> pd.DataFrame:
    start = pd.Timestamp(start)
    end = pd.Timestamp(end)
    return df[(df[COL_MONTH] >= start) & (df[COL_MONTH] <= end)]


def options_for(df: pd.DataFrame, col: str) -> list[str]:
    if col not in df.columns or df.empty:
        return []
    return sorted(df[col].dropna().unique().tolist())


# --------------------------------------------------------- aggregations -----

def _finish(agg: pd.DataFrame) -> pd.DataFrame:
    agg[COL_SIGNED] = agg[COL_STF] - agg[COL_STF_L1]
    agg[COL_DELTA] = agg[COL_SIGNED].abs()
    denom = agg[COL_STF_L1].abs()
    agg[COL_DELTA_PCT] = np.where(denom > 0, agg[COL_DELTA] / denom, np.nan)
    return agg


def exception_table(df: pd.DataFrame, group_cols: list[str],
                    top_n: int = 30, only_changed: bool = True) -> pd.DataFrame:
    """Aggregate over the selected horizon and return the top N by kg change.

    Rows whose forecast did not move are dropped by default: an exception list
    is only useful if everything on it is an exception.
    """
    if df.empty:
        return pd.DataFrame(columns=group_cols + [COL_STF, COL_STF_L1,
                                                  COL_DELTA, COL_DELTA_PCT])
    agg = (df.groupby(group_cols, observed=True, dropna=False)[[COL_STF, COL_STF_L1]]
             .sum().reset_index())
    agg = _finish(agg)
    if only_changed:
        agg = agg[agg[COL_DELTA] > 0]
    agg = agg.sort_values(COL_DELTA, ascending=False, kind="mergesort")
    cols = group_cols + [COL_STF, COL_STF_L1, COL_DELTA, COL_DELTA_PCT]
    return agg[cols].head(top_n).reset_index(drop=True)


def changed_group_count(df: pd.DataFrame, group_cols: list[str]) -> int:
    """How many groups in scope moved at all versus lag 1."""
    if df.empty:
        return 0
    agg = df.groupby(group_cols, observed=True, dropna=False)[[COL_STF, COL_STF_L1]].sum()
    return int(((agg[COL_STF] - agg[COL_STF_L1]).abs() > 0).sum())


def monthly_trend(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=[COL_MONTH, COL_STF, COL_STF_L1])
    out = (df.groupby(COL_MONTH, observed=True)[[COL_STF, COL_STF_L1]]
             .sum().reset_index().sort_values(COL_MONTH))
    return out


def material_change_mix(df: pd.DataFrame, top_n: int = 30) -> tuple[pd.DataFrame, list[str]]:
    """Top N materials by total kg of forecast change, split by category.

    Returns the stacked frame (Material, Category, kg) and the material order
    (highest total change first).
    """
    empty = pd.DataFrame(columns=[COL_MATERIAL, COL_CATEGORY, COL_DELTA])
    if df.empty:
        return empty, []
    totals = (df.groupby(COL_MATERIAL, observed=True)[COL_DELTA]
                .sum().sort_values(ascending=False))
    totals = totals[totals > 0]
    order = totals.head(top_n).index.tolist()
    if not order:
        return empty, []
    sub = df[df[COL_MATERIAL].isin(order)]
    mix = (sub.groupby([COL_MATERIAL, COL_CATEGORY], observed=False)[COL_DELTA]
              .sum().reset_index())
    mix = mix[mix[COL_DELTA] > 0]
    return mix, order


def kpis(df: pd.DataFrame) -> dict:
    stf = float(df[COL_STF].sum()) if not df.empty else 0.0
    lag = float(df[COL_STF_L1].sum()) if not df.empty else 0.0
    abs_delta = float(df[COL_DELTA].sum()) if not df.empty else 0.0
    combos = int(df.groupby([COL_MATERIAL, COL_SHIPTO], observed=True).ngroups) if not df.empty else 0
    changed = 0
    if not df.empty:
        per_combo = df.groupby([COL_MATERIAL, COL_SHIPTO], observed=True)[COL_DELTA].sum()
        changed = int((per_combo > 0).sum())
    return {
        "stat_forecast": stf,
        "lag1_forecast": lag,
        "net_delta": stf - lag,
        "abs_delta": abs_delta,
        "abs_delta_pct": (abs_delta / abs(lag)) if lag else float("nan"),
        "combos": combos,
        "combos_changed": changed,
    }


# ------------------------------------------------------------- display ------

def short_name(value: str) -> str:
    """'Cleaning__BL02' -> 'Cleaning'; leaves plain values untouched."""
    if isinstance(value, str) and "__" in value:
        return value.split("__")[0].strip()
    return value


def shorten(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    out = df.copy()
    for c in cols:
        if c in out.columns:
            out[c] = out[c].map(short_name)
    return out

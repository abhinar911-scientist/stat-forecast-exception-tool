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
COL_MAT_CODE = "Material Code"

# Forecast engines leave floating-point residue; anything under this many kg is
# not a real change and must not be counted as an exception.
KG_TOLERANCE = 0.5

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
    CAT_NO_CHANGE: "#1c5a92",   # navy
    CAT_PATTERN: "#2a9d8f",     # teal
    CAT_STATUS: "#7b5ea7",      # violet
    CAT_BOTH: "#c98a2b",        # amber
}


class DataError(Exception):
    """Raised when the uploaded workbook cannot be used.

    ``detail`` carries the technical reason for the logs; ``args[0]`` is what the
    user sees and deliberately never names the report's columns.
    """

    def __init__(self, message: str, detail: str = ""):
        super().__init__(message)
        self.detail = detail or message


def user_message(exc: Exception) -> str:
    return str(exc)


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
            f"This does not look like the Arkieva Statistical Forecast Exception "
            f"list export — {len(missing)} expected field(s) are missing. Please "
            f"re-run the standard report and upload it again.",
            detail="missing columns: " + ", ".join(missing),
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

    df[COL_MAT_CODE] = df[COL_MATERIAL].map(material_code)
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
        agg = agg[agg[COL_DELTA] > KG_TOLERANCE]
    agg = agg.sort_values(COL_DELTA, ascending=False, kind="mergesort")
    cols = group_cols + [COL_STF, COL_STF_L1, COL_DELTA, COL_DELTA_PCT]
    return agg[cols].head(top_n).reset_index(drop=True)


def changed_group_count(df: pd.DataFrame, group_cols: list[str]) -> int:
    """How many groups in scope moved at all versus lag 1."""
    if df.empty:
        return 0
    agg = df.groupby(group_cols, observed=True, dropna=False)[[COL_STF, COL_STF_L1]].sum()
    return int(((agg[COL_STF] - agg[COL_STF_L1]).abs() > KG_TOLERANCE).sum())


def monthly_trend(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=[COL_MONTH, COL_STF, COL_STF_L1])
    out = (df.groupby(COL_MONTH, observed=True)[[COL_STF, COL_STF_L1]]
             .sum().reset_index().sort_values(COL_MONTH))
    return out


def material_change_mix(df: pd.DataFrame, top_n: int = 30) -> tuple[pd.DataFrame, list[str]]:
    """Top N materials by kg of forecast change, split by segmentation category.

    Like every other measure here the delta is taken on the aggregate: months
    are summed per Material x Category first, then the absolute change is read
    off that total.
    """
    empty = pd.DataFrame(columns=[COL_MATERIAL, COL_CATEGORY, COL_DELTA])
    if df.empty:
        return empty, []

    mix = (df.groupby([COL_MATERIAL, COL_CATEGORY], observed=False)[[COL_STF, COL_STF_L1]]
             .sum().reset_index())
    mix[COL_DELTA] = (mix[COL_STF] - mix[COL_STF_L1]).abs()
    mix = mix[mix[COL_DELTA] > KG_TOLERANCE]
    if mix.empty:
        return empty, []

    totals = (mix.groupby(COL_MATERIAL, observed=True)[COL_DELTA]
                 .sum().sort_values(ascending=False))
    order = totals.head(top_n).index.tolist()
    mix = mix[mix[COL_MATERIAL].isin(order)]
    return mix[[COL_MATERIAL, COL_CATEGORY, COL_DELTA]], order


def kpis(df: pd.DataFrame) -> dict:
    """Headline numbers for the current scope.

    Every figure is computed on aggregates, never on raw rows:

    * ``net_delta`` is the portfolio total this month minus the total committed
      last month — the volume the plan actually moved by.
    * ``gross_delta`` sums the absolute change of each Material x Ship To
      combination **after** its months are added up, so a rise in March and an
      equal fall in April inside one combination net out instead of being
      counted twice. This is the churn behind a small net number.
    * ``combos_changed`` counts combinations that moved by more than
      ``KG_TOLERANCE`` kg, which keeps floating-point residue out of the count.
    """
    blank = {"stat_forecast": 0.0, "lag1_forecast": 0.0, "net_delta": 0.0,
             "net_delta_pct": float("nan"), "gross_delta": 0.0,
             "gross_delta_pct": float("nan"), "combos": 0, "combos_changed": 0}
    if df.empty:
        return blank

    stf = float(df[COL_STF].sum())
    lag = float(df[COL_STF_L1].sum())
    net = stf - lag

    combo = df.groupby([COL_MATERIAL, COL_SHIPTO], observed=True)[[COL_STF, COL_STF_L1]].sum()
    combo_delta = (combo[COL_STF] - combo[COL_STF_L1]).abs()
    gross = float(combo_delta.sum())

    return {
        "stat_forecast": stf,
        "lag1_forecast": lag,
        "net_delta": net,
        "net_delta_pct": (net / abs(lag)) if lag else float("nan"),
        "gross_delta": gross,
        "gross_delta_pct": (gross / abs(lag)) if lag else float("nan"),
        "combos": int(len(combo)),
        "combos_changed": int((combo_delta > KG_TOLERANCE).sum()),
    }


# ------------------------------------------------------------- display ------

def material_code(value: str) -> str:
    """'AG 6202 210 KG PTH DR__8003955' -> '8003955'."""
    if isinstance(value, str) and "__" in value:
        return value.rsplit("__", 1)[1].strip()
    return ""


def split_material(table: pd.DataFrame) -> pd.DataFrame:
    """Give the table a Material Code column and leave the description intact."""
    if COL_MATERIAL not in table.columns:
        return table
    out = table.copy()
    codes = out[COL_MATERIAL].map(material_code)
    out[COL_MATERIAL] = out[COL_MATERIAL].map(short_name)
    out.insert(out.columns.get_loc(COL_MATERIAL), COL_MAT_CODE, codes)
    return out


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

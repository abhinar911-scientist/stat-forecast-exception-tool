#!/usr/bin/env python3
"""Generate a small synthetic Arkieva-shaped export for demos and testing.

    python scripts/make_sample_data.py sample/sample_arkieva_export.xlsx

No customer data — every name is invented.
"""
from __future__ import annotations

import sys
import pathlib
import numpy as np
import pandas as pd

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import data as D  # noqa: E402

RNG = np.random.default_rng(7)

BUSINESS = {
    "Cleaning__BL02": ["PF Chelates__PF_701_CHE", "PF Alkoxylates__PF_702_ALK"],
    "Personal Care__BL03": ["PF Solution & Bio__PF_703_SOL"],
    "Cons.Goods&Packaging__BL05": ["PF Polymers__PF_705_POL"],
}
REGIONS = ["Europe", "North America", "South America"]
PATTERNS = ["Stable", "Erratic", "Seasonal", "Sporadic", "Linear"]
STATUSES = ["Active", "Active New", "Sparse", "Inactive", "New Combination"]


def main(out: str) -> None:
    months = pd.date_range("2026-11-01", periods=12, freq="MS")
    rows = []
    for bl, pls in BUSINESS.items():
        for pl in pls:
            for i in range(14):
                material = f"DEMO MATERIAL {bl[:3].upper()}{i:02d}__90{i:03d}"
                region = REGIONS[i % len(REGIONS)]
                parent = f"DEMO CUSTOMER {chr(65 + i % 8)}__4100{i:04d}"
                ship_to = f"{parent.split('__')[0]} --- Site {i % 3}__4200{i:04d}"
                pat = PATTERNS[i % len(PATTERNS)]
                sta = STATUSES[i % len(STATUSES)]
                # a quarter of the combinations get re-segmented this cycle
                pat_l1 = PATTERNS[(i + 1) % len(PATTERNS)] if i % 4 == 1 or i % 4 == 3 else pat
                sta_l1 = STATUSES[(i + 2) % len(STATUSES)] if i % 4 >= 2 else sta
                level = float(RNG.integers(500, 40_000))
                drift = float(RNG.normal(0, 0.12))
                for m in months:
                    season = 1 + 0.15 * np.sin(m.month / 12 * 2 * np.pi)
                    lag1 = level * season
                    curr = lag1 * (1 + drift) if i % 5 else lag1
                    rows.append({
                        D.COL_BL: bl, D.COL_PL: pl, D.COL_PARENT: parent,
                        D.COL_SHIPTO: ship_to, D.COL_REGION: region,
                        D.COL_MATERIAL: material,
                        D.COL_ABC: "ABC"[i % 3], D.COL_VAR: "LMH"[i % 3],
                        D.COL_STATUS: sta, D.COL_STATUS_L1: sta_l1,
                        D.COL_PATTERN: pat, D.COL_PATTERN_L1: pat_l1,
                        D.COL_REVIEW: bool(i % 2), D.COL_REVIEW_L1: bool(i % 2),
                        D.COL_MONTH: m,
                        D.COL_STF: round(curr, 2),
                        D.COL_STF_L1: round(lag1, 2),
                    })
    df = pd.DataFrame(rows)
    path = pathlib.Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(path, index=False, sheet_name="Statistical Forecast")
    print(f"{path} — {len(df):,} rows")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "sample/sample_arkieva_export.xlsx")

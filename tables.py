"""Exhibit-style HTML tables.

Streamlit's native dataframe is a spreadsheet widget; a review pack wants an
exhibit. These render a consulting-style table: a kicker and title, a rule under
the header, no vertical gridlines, right-aligned figures, and colour used once —
on the deltas that breach the review threshold.
"""
from __future__ import annotations

import html
import pandas as pd

import data as D

NUMERIC = {D.COL_STF, D.COL_STF_L1, D.COL_DELTA, D.COL_DELTA_PCT}

# Relative column widths; the table uses a fixed layout so nothing overflows.
WIDTHS = {
    D.COL_BL: 9.0, D.COL_PL: 9.0, D.COL_MAT_CODE: 7.0, D.COL_MATERIAL: 17.0,
    D.COL_REGION: 8.5, D.COL_ABC: 4.6, D.COL_PARENT: 13.0,
    D.COL_STF: 10.0, D.COL_STF_L1: 11.0, D.COL_DELTA: 10.0, D.COL_DELTA_PCT: 8.0,
}

HEADERS = {
    D.COL_BL: "Business Line",
    D.COL_PL: "Product Line",
    D.COL_MAT_CODE: "Material<br>Code",
    D.COL_MATERIAL: "Material",
    D.COL_REGION: "Ship To<br>Sub Region",
    D.COL_ABC: "ABC",
    D.COL_PARENT: "Parent<br>Customer",
    D.COL_STF: "Statistical<br>Forecast (kg)",
    D.COL_STF_L1: "Stat Forecast<br>Committed Lag 1 (kg)",
    D.COL_DELTA: "Absolute Delta<br>vs Lag 1 (kg)",
    D.COL_DELTA_PCT: "Delta %<br>vs Lag 1",
}

CSS = """
<style>
.exhibit {
  --ink:        #10151c;
  --ink-soft:   #5a6472;
  --rule:       #c9ced6;
  --rule-light: #e8eaee;
  --accent:     #0b3d6b;
  --flag-bg:    #fdeaea;
  --flag-ink:   #9a1f1f;
  font-family: Inter, "Segoe UI", system-ui, sans-serif;
  margin: 0 0 0.35rem 0;
}
.exhibit-kicker {
  font-size: 0.68rem; font-weight: 700; letter-spacing: 0.1em;
  text-transform: uppercase; color: var(--accent); margin-bottom: 0.2rem;
}
.exhibit-title {
  font-size: 1.06rem; font-weight: 650; color: var(--ink);
  letter-spacing: -0.01em; margin-bottom: 0.15rem;
}
.exhibit-sub { font-size: 0.82rem; color: var(--ink-soft); margin-bottom: 0.1rem; }
.exhibit-rule { height: 3px; background: var(--accent); width: 42px; margin: 0.5rem 0 0.7rem 0; }
.exhibit-scroll { max-height: 620px; overflow: auto; border-bottom: 1px solid var(--rule); }
table.exhibit-table {
  border-collapse: collapse; width: 100%; table-layout: fixed;
  font-size: 0.79rem;
}
table.exhibit-table thead th {
  position: sticky; top: 0; z-index: 2; background: #fff;
  font-size: 0.70rem; font-weight: 700; letter-spacing: 0.02em;
  color: var(--ink-soft); text-transform: uppercase;
  text-align: left; vertical-align: bottom;
  padding: 0.45rem 0.55rem 0.4rem 0.55rem;
  border-bottom: 1.5px solid var(--ink);
  overflow-wrap: normal; word-break: keep-all; hyphens: none;
}
table.exhibit-table thead th.num { text-align: right; }
table.exhibit-table thead th.rank { width: 2.2rem; text-align: right; }
table.exhibit-table tbody td {
  padding: 0.38rem 0.55rem; color: var(--ink); overflow-wrap: anywhere;
  border-bottom: 1px solid var(--rule-light); vertical-align: top;
}
table.exhibit-table tbody tr:hover td { background: #f5f7fa; }
table.exhibit-table td.num {
  text-align: right; font-variant-numeric: tabular-nums;
  white-space: nowrap; overflow-wrap: normal;
}
table.exhibit-table td.new { color: var(--flag-ink); font-weight: 650; }
table.exhibit-table td.rank { text-align: right; color: var(--ink-soft);
  font-variant-numeric: tabular-nums; white-space: nowrap;
  overflow-wrap: normal; }
table.exhibit-table td.dim { color: var(--ink-soft); }
table.exhibit-table td.flag {
  background: var(--flag-bg); color: var(--flag-ink); font-weight: 650;
  box-shadow: inset 2px 0 0 var(--flag-ink);
}
.exhibit-foot {
  font-size: 0.74rem; color: var(--ink-soft);
  margin: 0.45rem 0 0.1rem 0; display: flex; gap: 1.1rem; flex-wrap: wrap;
}
.exhibit-chip {
  display: inline-flex; align-items: center; gap: 0.35rem;
}
.exhibit-chip::before {
  content: ""; width: 0.62rem; height: 0.62rem; border-radius: 2px;
  background: var(--flag-bg); box-shadow: inset 2px 0 0 var(--flag-ink);
}
</style>
"""


def _fmt(col: str, value) -> str:
    if pd.isna(value):
        # Only the percentage can be blank, and only when lag 1 was zero.
        return "new" if col == D.COL_DELTA_PCT else ""
    if col == D.COL_DELTA_PCT:
        return f"{value * 100:,.1f}%"
    if col in NUMERIC:
        return f"{value:,.0f}"
    return html.escape(str(value))


def exhibit(table: pd.DataFrame, columns: list[str], *, kicker: str, title: str,
            subtitle: str, threshold: float, footnote: str = "") -> str:
    """Render one ranked exception table as an HTML exhibit."""
    total_w = 3.2 + sum(WIDTHS.get(c, 9.0) for c in columns)
    group = ['<col style="width:%.2f%%">' % (3.2 / total_w * 100)]
    group += ['<col style="width:%.2f%%">' % (WIDTHS.get(c, 9.0) / total_w * 100)
              for c in columns]
    head = "".join(
        f'<th class="{"num" if c in NUMERIC else ""}">{HEADERS.get(c, c)}</th>'
        for c in columns
    )
    dim = {D.COL_BL, D.COL_PL, D.COL_MAT_CODE, D.COL_REGION}

    body = []
    for rank, (_, row) in enumerate(table.iterrows(), start=1):
        cells = [f'<td class="rank">{rank}</td>']
        pct = row.get(D.COL_DELTA_PCT)
        # A combination with no lag 1 volume is new: there is no percentage to
        # compare, but it is exactly the kind of row the review should see.
        breach = pct > threshold if pd.notna(pct) else row[D.COL_DELTA] > D.KG_TOLERANCE
        for c in columns:
            classes = []
            if c in NUMERIC:
                classes.append("num")
            if c in dim:
                classes.append("dim")
            if breach and c in (D.COL_DELTA, D.COL_DELTA_PCT):
                classes.append("flag")
            if c == D.COL_DELTA_PCT and pd.isna(pct):
                classes.append("new")
            cls = f' class="{" ".join(classes)}"' if classes else ""
            cells.append(f"<td{cls}>{_fmt(c, row[c])}</td>")
        body.append(f"<tr>{''.join(cells)}</tr>")

    pcts = table[D.COL_DELTA_PCT]
    flagged = int(((pcts > threshold) | pcts.isna()).sum())
    foot = (
        f'<div class="exhibit-foot">'
        f'<span class="exhibit-chip">Shaded = change above the '
        f'{threshold * 100:.0f}% review threshold ({flagged} of {len(table)} rows)</span>'
        + (f"<span>{html.escape(footnote)}</span>" if footnote else "")
        + "</div>"
    )

    return (
        f'<div class="exhibit">'
        f'<div class="exhibit-kicker">{html.escape(kicker)}</div>'
        f'<div class="exhibit-title">{html.escape(title)}</div>'
        f'<div class="exhibit-sub">{html.escape(subtitle)}</div>'
        f'<div class="exhibit-rule"></div>'
        f'<div class="exhibit-scroll"><table class="exhibit-table">'
        f'<colgroup>{"".join(group)}</colgroup>'
        f'<thead><tr><th class="rank">#</th>{head}</tr></thead>'
        f"<tbody>{''.join(body)}</tbody></table></div>"
        f"{foot}</div>"
    )

# Statistical Forecast Exception List

A Streamlit dashboard that turns the monthly Arkieva statistical-forecast extract
into a ranked exception list, so the step-02 review process starts from the
changes that actually matter instead of the full ~5,000-material portfolio.

It answers three questions for any slice of the portfolio:

1. **Which combinations moved the most since last month?** Top 30 tables at
   Material × Ship To Sub Region, and the same ranking broken down by Parent
   Customer.
2. **Did the total forecast shift, and in which months?** Current statistical
   forecast vs. Committed Lag 1 across the M+1 … M+13 horizon.
3. **Is the movement re-segmentation or model refit?** Top 30 materials by kg of
   change, split into No Change / Pattern Change / Status Change / Status and
   Pattern Change.

---

## 1. What the app expects as input

The Arkieva *Statistical Forecast Exception list input data* export (`.xlsx`),
one row per Material × Ship To × Month over M+1 to M+13. These columns must be
present, spelled exactly like this:

| Column | Used for |
|---|---|
| `Business Line` | filter, table column |
| `Product Line` | filter, table column |
| `Parent Cust` | filter, second table |
| `Ship To` | combination counting |
| `Ship To Sub Region` | filter, table column |
| `Material` | filter, table column, change chart |
| `Arkieva ABC` | filter |
| `Arkieva Variability` | filter |
| `Arkieva Active Status` / `… Lag 1` | change category |
| `Arkieva Pattern` / `… Lag 1` | change category |
| `Arkieva Review Req` / `… Lag 1` | filter |
| `Month` | horizon slider, trend chart |
| `Statistical Forecast (kg)` | all measures |
| `Statistical Forecast Committed Lag 1 (kg)` | all measures |

Extra columns are ignored. A missing column produces a clear error naming it.

### How the numbers are calculated

Everything is aggregated **first** over the selected filters and month range,
and the delta is taken on the aggregate — so a +500 kg move in March and a
−500 kg move in April inside the same horizon net to zero rather than
double-counting.

- `Absolute Delta vs Lag 1 (kg)` = `|Σ Statistical Forecast − Σ Committed Lag 1|`
- `Delta % vs Lag 1` = `Absolute Delta ÷ |Σ Committed Lag 1|`; shown as `new`
  when lag 1 is zero, and such rows are flagged
- Scorecards follow the same rule. **Net change** is the portfolio total minus
  the lag 1 total; **% change** is that over lag 1; **Gross change** totals each
  Material × Ship To combination over the horizon first and then sums the
  absolute changes, so offsetting months inside one combination are not counted
  twice. Movements below 0.5 kg are floating-point residue and are ignored.
- Deltas above 5% of lag 1 are shaded in both tables; change `DELTA_THRESHOLD`
  in `app.py` to move that line.
- Tables are ranked by absolute kg (volume weighted), largest first, and rows
  with no movement are dropped — an exception list only carries exceptions.
- Change categories compare this month's Arkieva segmentation with last
  month's. By default a move between Arkieva's not-classified tokens (`-`,
  `Unknown`, blank) is **not** counted as a change; the sidebar toggle
  "Ignore moves between unclassified codes" turns that off.

---

## 2. Running it locally

```bash
git clone https://github.com/<your-org>/stat-forecast-exception-tool.git
cd stat-forecast-exception-tool

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .streamlit/secrets.toml.example .streamlit/secrets.toml
python scripts/hash_password.py    # paste the hash into secrets.toml

streamlit run app.py
```

The app opens at http://localhost:8501. Sign in, then upload the Arkieva export
in the sidebar. `sample/sample_arkieva_export.xlsx` is fully synthetic test data
you can use to try the app without real customer figures.

Run the tests with `python -m pytest tests -q`.

---

## 3. Deploying to Streamlit Community Cloud

**Step 1 — push the repo to GitHub.**

```bash
git init
git add .
git commit -m "Statistical Forecast Exception List tool"
git branch -M main
git remote add origin https://github.com/<your-org>/stat-forecast-exception-tool.git
git push -u origin main
```

`.gitignore` already excludes `.streamlit/secrets.toml` and any stray `.xlsx`
drop — **never commit real secrets or Arkieva extracts.**

**Step 2 — create the app.** Go to https://share.streamlit.io → *Create app* →
*Deploy a public app from GitHub*, and fill in:

- Repository: `<your-org>/stat-forecast-exception-tool`
- Branch: `main`
- Main file path: `app.py`
- (Advanced settings) Python version: 3.11 or later

**Step 3 — add the users before the first run.** Still in *Advanced settings*,
paste your user list into the **Secrets** box (format in section 4), then
*Deploy*. The build takes a couple of minutes while `requirements.txt` installs.

**Step 4 — lock down who can open it.** On the free tier a deployed app URL is
public: anyone with the link reaches the login screen. The login gate stops them
going further, but for internal data also set *Settings → Sharing* to restrict
viewers to invited accounts if your plan supports it.

**Deploying anywhere else.** The app is a plain Streamlit app, so the same code
runs on an internal server or container:

```bash
pip install -r requirements.txt
streamlit run app.py --server.port 8501 --server.address 0.0.0.0
```

Put the secrets file at `.streamlit/secrets.toml` next to `app.py`, or set the
same values as environment variables via your platform's secret store.

---

## 4. Adding users and passwords

Users live in secrets — never in the code — so adding one needs no redeploy of
the repository.

**Step 1 — generate a bcrypt hash** (on your machine, inside the venv):

```bash
python scripts/hash_password.py
# Password: ········
# $2b$12$u1kG3n...  ← copy this whole line
```

**Step 2 — add a block per user.** Locally that is `.streamlit/secrets.toml`;
on Streamlit Cloud it is *your app → ⋮ → Settings → Secrets*:

```toml
[auth]

[auth.users.abhi]
name = "Abhi"
password_hash = "$2b$12$u1kG3n..."

[auth.users.j.smith]
name = "J. Smith"
password_hash = "$2b$12$qQ8vTz..."
```

The key after `auth.users.` is the username typed at sign-in (case-insensitive).

**Step 3 — save.** Streamlit Cloud restarts the app automatically, usually
within ~30 seconds. The new user can sign in immediately.

**To change a password**, generate a new hash and replace that user's
`password_hash`. **To remove someone**, delete their `[auth.users.<name>]` block
— they are locked out at their next page load.

Notes on the gate:
- Only bcrypt hashes are stored; plain passwords never reach the repo or the
  server config.
- Eight failed attempts lock the form until the page is reloaded.
- Sessions are per browser tab: closing the tab signs the user out.
- This is a single shared gate, not SSO. If the tool ends up holding more
  sensitive data than the extract, move it behind Nouryon SSO on an internal
  host rather than widening this list.

---

## 5. Using the dashboard

- **Sidebar filters** cascade: pick a Business Line and the Product Line,
  Material and Parent Customer lists narrow to what is still reachable. An empty
  filter means "all". *Reset all filters* clears everything.
- **Forecast horizon** slider defaults to the full M+1 … M+13 window; drag
  either handle to focus on, say, the next quarter. Every KPI, table and chart
  obeys it.
- **Short names** strips the `__CODE` suffix Arkieva appends. Downloads always
  carry the full coded values so they join back to Arkieva cleanly.
- Both tables have a **Download CSV** button for the review pack.

---

## 6. Project layout

```
app.py                     Streamlit UI: filters, horizon, KPIs, tabs
data.py                    loading, validation, deltas, categories, aggregations
charts.py                  Plotly figures (trend line, stacked change bars)
auth.py                    bcrypt login gate
scripts/hash_password.py   password hash generator
scripts/make_sample_data.py synthetic demo export generator
sample/                    synthetic demo export
tables.py                  exhibit-style HTML tables
tests/test_logic.py        unit tests for every metric rule
USER_GUIDE.md              how to run the monthly review with this tool
.streamlit/config.toml     theme and upload limit (200 MB)
.streamlit/secrets.toml    users — local only, never committed
```

---

## 7. Users configured in this bundle

`.streamlit/secrets.toml` (and `.example`) already carry bcrypt hashes for four
accounts: **Abhishek, Sara, Tonny, Michael** — the passwords agreed separately.
Usernames are case-insensitive at sign-in.

`secrets.toml` is gitignored, so it will not reach GitHub. After deploying,
paste the same block into the Streamlit Cloud Secrets box (section 4). Have each
person change their password once they are set up: run
`python scripts/hash_password.py` and swap that user's `password_hash`.

# Trans Name Changes → Baby Name Trends

## Permissions

Bash(*) is granted for this project. Use freely but **never destructively** — no deleting files, no force-pushes, no dropping data.

## Research Question

**Hypothesis:** Trans name changes are predictive of future baby naming trends. Trans people are cultural early adopters — names they choose today become mainstream baby names 5-10 years later.

For full findings and limitations, see `docs/REPORT.md`.

---

## Project Status

**Scrape:** Complete — 1,234/1,235 PDFs cached, 149,602 records extracted
**Analysis:** Complete — all outputs in `data/processed/`
**Web app:** Built — serve with `python -m http.server 8080 --directory app`

---

## Directory Structure

```
babynames/
├── data/
│   ├── raw/                    ← source data (do not modify)
│   │   ├── ontario_baby_names_female.csv
│   │   ├── ontario_baby_names_male.csv
│   │   └── ontario_name_changes.csv
│   └── processed/              ← analysis outputs
│       ├── name_changes_scored.csv
│       ├── likely_trans_name_changes.csv
│       ├── curve_scores.csv
│       ├── curve_score_report.txt
│       ├── correlation_results_*.csv
│       ├── granger_causality.csv
│       └── *.png (static plots)
│
├── scripts/
│   ├── download_baby_names.py  ← download raw baby name CSVs
│   ├── scrape.py               ← scrape gazette PDFs → ontario_name_changes.csv
│   ├── analyze.py              ← full statistical analysis
│   ├── visualize.py            ← generate Plotly HTML visualizations
│   ├── audit.py                ← diagnose PDF parser yield by year
│   ├── pipeline.py             ← orchestrate full overnight workflow
│   ├── export_web_data.py      ← export JSON for web app
│   └── tests/
│       └── test_curve_scores.py
│
├── app/                        ← web application (static, no server needed)
│   ├── index.html
│   ├── css/style.css
│   ├── js/
│   └── data/                   ← pre-generated JSON (from export_web_data.py)
│
├── docs/
│   ├── REPORT.md               ← research findings + limitations
│   └── WEBAPP_SPEC.md          ← web app design document
│
├── audit/                      ← parser audit outputs
├── gazette_pdfs/               ← 1,234 cached PDFs (DO NOT DELETE)
├── viz/                        ← legacy standalone Plotly HTMLs
├── CLAUDE.md
└── requirements.txt
```

---

## Setup

```bash
source .venv/Scripts/activate   # always activate venv first
pip install -r requirements.txt
```

---

## Running the Web App

```bash
# One-time: generate JSON data files for the web app
python scripts/export_web_data.py \
  --raw-dir data/raw \
  --processed-dir data/processed \
  --output-dir app/data

# Serve locally
python -m http.server 8080 --directory app
# Open http://localhost:8080
```

---

## Full Pipeline Commands

```bash
# 1. Download baby name data (already done)
python scripts/download_baby_names.py

# 2. Scrape gazette PDFs (already done; resume with --skip-download if PDFs cached)
python scripts/scrape.py \
    --start-year 2000 --end-year 2024 \
    --output data/raw/ontario_name_changes.csv \
    --cache-dir gazette_pdfs

# 3. Statistical analysis
python scripts/analyze.py \
    -n data/raw/ontario_name_changes.csv \
    -f data/raw/ontario_baby_names_female.csv \
    -m data/raw/ontario_baby_names_male.csv \
    -o data/processed/ \
    --thresholds 0.2,0.5,0.7

# 4. Generate standalone Plotly HTML visualizations (legacy)
python scripts/visualize.py \
    -n data/raw/ontario_name_changes.csv \
    -f data/raw/ontario_baby_names_female.csv \
    -m data/raw/ontario_baby_names_male.csv \
    -r data/processed/ \
    -o viz/

# 5. Run tests
python scripts/tests/test_curve_scores.py

# 6. Audit parser yield (optional diagnostics)
python scripts/audit.py --cache-dir gazette_pdfs --output-dir audit

# 7. Export web app data (after step 3)
python scripts/export_web_data.py \
    --raw-dir data/raw \
    --processed-dir data/processed \
    --output-dir app/data
```

---

## Key Results

| Metric | Value |
|---|---|
| All name changes mean lag | −0.30 years (gazette lags baby trends) |
| Likely-trans mean lag | **+0.86 years** ← trans filter flips the sign |
| MTF mean lag | +1.71y (likely artifact — see REPORT.md §5.2) |
| FTM mean lag | +0.78y |
| MTF vs FTM t-test | p=0.21 (not significant) |
| Granger causality | Non-significant at all lags 1–5 |
| Curve score (all) | −0.104 (everyone is somewhat behind the curve) |
| Curve score (trans) | −0.121 |
| Time trend | +0.0024/yr (p=0.26, not significant) |

---

## Known Limitations

- **Trans opt-out (2006+):** Trans people can request non-publication in the Gazette since 2006 — systematic underrepresentation in recent data
- **MTF confound:** Positive MTF lag is likely artifact from two declining time series correlating, not genuine prediction
- **Gender delta is coarse:** Binary baby name gender coding; gender-neutral names missed; threshold is arbitrary
- **Ontario only:** Naming trends may differ elsewhere
- **PDF parsing fragility:** ~2 PDFs unreadable (CID encoding); format changed across 25 years

---

## File Notes

- `gazette_pdfs/` — 1,234 cached PDFs (1.9 GB). **Do not delete** — re-downloading takes 3–5 hours.
- `data/raw/ontario_name_changes.csv` — 149,602 records. Source of truth for analysis.
- `data/processed/` — All analysis outputs. Regenerate with `scripts/analyze.py`.
- `app/data/` — JSON exports for web app. Regenerate with `scripts/export_web_data.py`.

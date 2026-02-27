# Trans Name Changes → Baby Name Trends

Do trans people function as early adopters of baby naming trends? This project tests the hypothesis that names chosen by trans people in legal name changes predict which names become popular for babies years later.

**Full findings and methodology:** [docs/REPORT.md](docs/REPORT.md)

---

## Key Findings

- **Trans-coded name changes lead baby name trends by +0.58 years** on average (vs. −0.11y for all name changes), consistent with the early-adopter hypothesis — though effect size is modest.
- **All groups choose past-peak names** (negative curve scores), but female-coded trans name changes show the most behind-curve choices (mean −0.137), likely because many popular trans names (EMMA, OLIVIA, SOPHIA) peaked as baby names years earlier.
- **No macro-level Granger causality** detected at the aggregate time series level — the signal exists at the individual name level but doesn't show up as a population-wide causal pattern.
- **9,511 trans-coded records** identified from 72,013 total name change records (1,234 Ontario Gazette issues, 2000–2024).

---

## Web App

An interactive explorer for browsing names, lag correlations, curve scores, and the trans vs. baby name comparison is in `app/`.

```bash
python -m http.server 8080 --directory app
# Open http://localhost:8080
```

No build step. Works over `file://` or any static host (GitHub Pages, Netlify, etc.).

---

## Reproducing the Analysis

**Prerequisites:** Python 3.9+, ~2 GB disk space for PDFs (cached after first run).

```bash
# 1. Create and activate virtual environment
python -m venv .venv
source .venv/Scripts/activate   # Windows
# source .venv/bin/activate     # macOS/Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Download Ontario baby name data (~3 MB)
python scripts/download_baby_names.py

# 4. Scrape Ontario Gazette name changes (1,234 PDFs — takes ~3 hrs, rate-limited)
python scripts/scrape.py --start-year 2000 --end-year 2024 --output data/raw/ontario_name_changes.csv

# 5. Run statistical analysis
python scripts/analyze.py \
  -n data/raw/ontario_name_changes.csv \
  -f data/raw/ontario_baby_names_female.csv \
  -m data/raw/ontario_baby_names_male.csv \
  -o data/processed/

# 6. Export JSON for web app
python scripts/export_web_data.py \
  --raw-dir data/raw \
  --processed-dir data/processed \
  --output-dir app/data
```

The `app/data/` JSON files are pre-computed and included in the repo so you can run the web app without re-running the full pipeline.

---

## Data & Privacy

**What's in this repo:**
- `app/data/*.json` — pre-computed analysis results containing only *new* first names, years, and aggregate statistics. No old names, no last names, no matched pairs.
- `audit/` — per-PDF parser diagnostics
- `data/processed/curve_score_report.txt`, `granger_causality.csv`, `mtf_ftm_ttest.txt` — key statistical outputs

**What's excluded:**
- `data/raw/ontario_name_changes.csv` — the raw gazette extraction includes old first names. For trans people, the old name is their deadname. It is excluded from this repo and never surfaced in the web app.
- `data/raw/ontario_baby_names_*.csv` — public Ontario government data, regenerable via `scripts/download_baby_names.py`
- `gazette_pdfs/` — 1.9 GB of cached PDFs, regenerable via the scraper
- `data/processed/*.csv` — intermediate analysis files, regenerable

---

## Project Structure

```
babynames/
├── scripts/
│   ├── scrape.py                 ← Ontario Gazette PDF scraper
│   ├── analyze.py                ← Statistical analysis (lag, curve score, Granger)
│   ├── visualize.py              ← Static Plotly chart generator
│   ├── export_web_data.py        ← Exports JSON for web app
│   ├── download_baby_names.py    ← Downloads Ontario baby name CSVs
│   ├── audit.py                  ← PDF parser diagnostics
│   ├── pipeline.py               ← End-to-end orchestration
│   └── tests/test_curve_scores.py
├── app/                          ← Static web app (no build step)
│   ├── index.html
│   ├── css/style.css
│   ├── js/                       ← main.js, charts.js, data.js, explorer.js
│   └── data/                     ← Pre-computed JSON (safe to publish)
├── docs/
│   └── REPORT.md                 ← Full research report
├── audit/                        ← Parser yield diagnostics
├── data/
│   ├── raw/                      ← gitignored (privacy + size)
│   └── processed/                ← gitignored except summary text files
├── requirements.txt
├── guide.md                      ← Detailed execution guide
└── CLAUDE.md                     ← Developer notes
```

---

## Limitations

The key caveat: since 2006, trans people in Ontario can opt out of Gazette publication. This means the dataset systematically under-represents trans name changes in recent years. See [docs/REPORT.md](docs/REPORT.md) §5 for full discussion of limitations.

---

## Data Sources

- **Ontario Gazette name changes** (2000–2024): [ontario.ca](https://www.ontario.ca/search/ontario-gazette)
- **Ontario baby names** (1913–2023): [Ontario Open Data](https://data.ontario.ca/dataset/ontario-top-baby-names-male) ([female](https://data.ontario.ca/dataset/ontario-top-baby-names-female))

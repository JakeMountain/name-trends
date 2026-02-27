# Trans Name Changes → Baby Name Trends
## End-to-End Execution Guide

### The Hypothesis
Trans name changes are predictive of future baby naming trends—trans people are "ahead of the curve" on names.

### The Data
| Dataset | Source | Coverage | Format |
|---------|--------|----------|--------|
| Baby names | data.ontario.ca | 1913-2023 | CSV (ready) |
| Name changes | Ontario Gazette | 2000-2024 | PDF (needs scraping) |

### The Key Trick
The scraper captures **old name → new name**. Using baby name data (which is sex-tagged), we can infer the gender of each name and calculate a **gender delta**:

```
gender_delta = P(female|new_name) - P(female|old_name)
```

- `Michael → Michelle` = +0.99 (likely MTF)
- `Jennifer → James` = -0.99 (likely FTM)
- `John → Jonathan` = ~0 (no gender change)

Filter to `|gender_delta| > 0.7` and you get a cleaner trans-specific subset.

---

## Step 1: Setup

```bash
# Create project directory
mkdir trans-names && cd trans-names

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # or `venv\Scripts\activate` on Windows

# Install dependencies
pip install -r requirements.txt
```

---

## Step 2: Download Baby Names

```bash
python download_baby_names.py
```

**Output:**
- `ontario_baby_names_female.csv` (1913-2023, ~1.4 MB)
- `ontario_baby_names_male.csv` (1917-2023, ~1.2 MB)

**Format:** `name, year, count` — all names with 5+ occurrences that year.

---

## Step 3: Scrape Name Changes

### Test run first (5 issues, ~2 minutes):
```bash
python ontario_gazette_scraper.py \
    --start-year 2024 \
    --end-year 2024 \
    --limit 5 \
    --output test_names.csv \
    --verbose
```

Check `test_names.csv` looks reasonable.

### Full scrape (~3-5 hours):
```bash
python ontario_gazette_scraper.py \
    --start-year 2000 \
    --end-year 2024 \
    --output ontario_name_changes.csv
```

**What it does:**
1. Fetches Gazette index from ontario.ca (~1,300 issues)
2. Downloads each PDF (cached in `gazette_pdfs/`)
3. Extracts "Notice of Change of Name" sections
4. Parses old→new name pairs
5. Outputs CSV

**Output:** `ontario_name_changes.csv` with columns:
- `old_first_name`, `old_full_first`, `old_last_name`
- `new_first_name`, `new_full_first`, `new_last_name`  
- `gazette_date`, `gazette_volume`, `gazette_issue`

**Expected volume:** ~150,000-200,000 records

### Resume if interrupted:
PDFs are cached. Re-run with `--skip-download` to only process cached files:
```bash
python ontario_gazette_scraper.py \
    --start-year 2000 \
    --end-year 2024 \
    --skip-download \
    --output ontario_name_changes.csv
```

---

## Step 4: Run Analysis

```bash
python analyze_name_trends.py \
    --name-changes ontario_name_changes.csv \
    --baby-names-female ontario_baby_names_female.csv \
    --baby-names-male ontario_baby_names_male.csv \
    --output-dir results/ \
    --trans-threshold 0.7
```

**What it does:**

1. **Gender Delta Scoring**
   - Builds P(female|name) lookup from baby data
   - Scores every name change by gender delta
   - Flags likely MTF/FTM transitions
   - Outputs: `name_changes_scored.csv`, `likely_trans_name_changes.csv`

2. **Cross-Correlation Analysis** (run on all data + trans subset)
   - For each name in both datasets, calculates correlation at lags -10 to +10 years
   - Positive lag = name changes lead baby names
   - Outputs: `correlation_results_*.csv`, `lag_distribution_*.png`

3. **Emerging Names Analysis**
   - Tracks names appearing in name changes → do they increase in baby popularity later?
   - Statistical test for significance
   - Outputs: `emerging_names_*.csv`

4. **Pre-2006 Analysis**
   - Before trans opt-out existed
   - Cleaner signal for true trans naming patterns

---

## Step 5: Interpret Results

### Output files in `results/`:

| File | What it tells you |
|------|-------------------|
| `gender_delta_distribution.png` | Shape of gender shifts—spikes at ±1 suggest trans transitions |
| `likely_trans_name_changes.csv` | Your trans-specific subset |
| `lag_distribution_all.png` | Does the whole dataset show name changes leading? |
| `lag_distribution_likely_trans.png` | Does the trans subset show it more strongly? |
| `correlation_results_*.csv` | Per-name correlation and optimal lag |
| `emerging_names_*.csv` | Do name-change names later get more popular for babies? |

### What supports the hypothesis:
- **Positive lags** in the trans subset (name changes precede baby name popularity)
- **Stronger effect in likely-trans** vs all name changes
- **Stronger effect pre-2006** (before trans opt-out biased the data)
- **Significant positive** average frequency change in emerging names analysis

### What would falsify it:
- No difference between trans subset and general population
- Negative or zero lags (baby names leading, or no relationship)
- Pre-2006 showing same pattern as post-2006 (suggests trans opt-out didn't matter → effect isn't trans-specific)

---

## Caveats & Limitations

### Trans Opt-Out (2006+)
Since 2006, trans people can opt out of Gazette publication. Post-2006 data **underrepresents trans name changes**.

**Implication:** Pre-2006 data is cleaner. If you see a signal pre-2006 that weakens post-2006, that's actually *supportive*—the trans component dropped out.

### What "Name Changes" Actually Includes
- Career/stage names
- Divorce-related
- Immigration/anglicization
- Religious conversion
- Disliked names
- Abuse survivors
- Trans (with post-2006 underrepresentation)

The gender-delta filter helps isolate trans-specific changes.

### Ontario ≠ USA
Results may not generalize. Ontario has universal healthcare, different cultural context, etc.

---

## File Structure

```
trans-names/
├── download_baby_names.py       # Step 2
├── ontario_gazette_scraper.py   # Step 3
├── analyze_name_trends.py       # Step 4
├── requirements.txt
├── ontario_baby_names_female.csv
├── ontario_baby_names_male.csv
├── ontario_name_changes.csv
├── gazette_pdfs/                # Cached PDFs
│   └── gazette_v###_i##.pdf
└── results/                     # Analysis output
    ├── name_changes_scored.csv
    ├── likely_trans_name_changes.csv
    ├── gender_delta_distribution.png
    ├── correlation_results_all.csv
    ├── correlation_results_likely_trans.csv
    ├── lag_distribution_all.png
    ├── lag_distribution_likely_trans.png
    ├── emerging_names_all.csv
    └── emerging_names_likely_trans.csv
```

---

## Quick Reference

```bash
# Full pipeline
pip install -r requirements.txt
python download_baby_names.py
python ontario_gazette_scraper.py --start-year 2000 --end-year 2024 -o ontario_name_changes.csv
python analyze_name_trends.py -n ontario_name_changes.csv -f ontario_baby_names_female.csv -m ontario_baby_names_male.csv -o results/
```

---

## Extending This

### Tighter trans filter
Increase threshold: `--trans-threshold 0.9`

### Different time windows
Edit `periods` list in `run_emerging_names_analysis()` in the analysis script.

### Add US data
SSA baby names: https://www.ssa.gov/oact/babynames/limits.html
(But US name change data is fragmented—no clean source)

### Gender-neutral names
Current filter misses trans people choosing neutral names. Could add a separate analysis tracking movement *toward* the 0.4-0.6 P(female) range.
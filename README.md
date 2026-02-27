# A note from the human behind this project

I've been batting around a theory for the past few years. It goes like this:

- **Premise 1:** Naming oneself or another human being is at least in part a matter of taste.
- **Premise 2:** Taste in names is like taste in music or fashion, and like those tastes it's largely established in one's teens and early 20s.
  - **Inference 1:** People choose names that were in some meaningful way "determined" by their formative, taste-making period, even if they're chosen formally later on in life.
- **Premise 3:** On average, trans people legally transition (and therefore rename themselves) earlier than people have kids (and therefore name babies).
- **Premise 4:** Naming yourself is not meaningfully different than naming a baby, at least as far as picking a name goes.
  - **Inference 2:** We're all just picking names from our personal taste pot when we name someone (ourselves or others). Trans people do it earlier, on average, than parents.
- **Premise 5:** Trans people: they're just like us! The people changing their names in Ontario, Canada are similar enough to the people naming babies in Ontario, Canada. (Sometimes, they're the same people!)
  - **Inference 3:** People who reached the age of taste-maturity at similar times were issued similar personal-taste-pots, whether they are trans, parent, or trans-parent. 👻
- **Conclusion:** Trends in trans naming are predictive of future baby name trends.

Some challenges can be leveled against this argument, like:

- "**Premise 4 is obviously wrong!** I name myself with knowledge of who I am, where I am situated, and all that other junk, whereas a baby is just a blank slate upon which I project my hopes, dreams, and tasteful names." Sure. But there's an element of taste at play in both, and that's what I hope to capture. All that knowledge of who you are and where you're situated still has to collide with a set of acceptable names, and that set is at least partially an artifact of taste.
- "**Premise 2 is a vast oversimplification!** My grandmother loves Yeat and Playboi Carti; her taste clearly wasn't set in her 20s!" Good for grandma. My assertion is a population-level claim, and your sweet gran-gran is one of one. I still might be wrong, but at least w.r.t. music I've seen some good evidence for this.
- "**Premise 5 is simplistic!** Subcultures (religous, ethnic, regional, cultural) have different naming practices, and trans people often associate closely with other queer people in a subculture, so they're pulling from different personal-taste-pots than the average Ontarian." Yeah, true. But I bet there's still some age cohort bias in there, and maybe we can extract it.

I had so much fun making this argument all the time, I was almost sad to see my hypothesis finally tested. But alas, claude is now good enough that I ran out of excuses. I told claude to research potential datasets to empirically analyze this problem, then took its findings and handed them to claude code, which promptly wrote and executed everything you see before you.

There are challenges in the dataset as well as the analysis. I'll highlight two problems up here: transgender people can request for their name change to not be published in the Ontario Gazette (as of 2006, I think). Personally, I think that's great. It does, however, raise the issue that some unknown number of trans people are opted out of this dataset, and they may be correlated in ways that harm data quality — e.g. perhaps younger trans people are more aware of this exemption, skewing the average age of transition name changes higher. The other problem is with the analysis: there's no box by each Gazette posting that says "this is a trans name change", and the technique I (fine, claude) came up with is rudimentary. We calculate the gender delta (that's right, the *Gender Delta*) between old and new first name using their prevalence in the Ontario baby names dataset, and consider name changes "trans" when this delta is large (≤|0.7|). It's entirely possible this filter is missing huge swaths of gender-ambiguous names.

Ultimately, the picture is fuzzy. I won't be publishing my findings in the American (or Canadian) Journal of Predictive Naming, at least not without some serious p-hacking. I'm not good enough at statistics, or even good enough at coaxing claude to be good at statistics, to analyze and understand this data adequately. There are however some graphs, and the name explorer is fun to play with. The site is up on GitHub Pages here: [jakemountain.github.io/name-trends](https://jakemountain.github.io/name-trends)

*Every word that follows this section — indeed, every other line in this project — was written by claude. Thanks, claude.*

---

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

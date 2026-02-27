# Trans Name Changes as a Predictor of Baby Naming Trends
## Research Report — Ontario Gazette Analysis (2000–2024)

---

## 1. Research Question

**Hypothesis:** Trans people who legally change their names are cultural early adopters. The names they choose today will become popular baby names 5–10 years later.

This builds on a well-documented pattern in naming sociology: names diffuse through social strata over time (Lieberson 2000; Levitt & Dubner 2005). High-SES or culturally avant-garde groups adopt names first; those names then "trickle down" to broader adoption over years to decades. Trans people, as a group that actively selects names in adulthood — outside the defaults of family tradition or current baby-name trends — might function as a particularly early signal in this diffusion process.

The Ontario Gazette provides a rare opportunity to test this: it is a publicly accessible, legally mandated record of name changes with enough historical depth (2000–present) to allow for lag analysis against baby name frequency data.

---

## 2. Data

### Ontario Baby Names (1913–2023)
- **Source:** data.ontario.ca (Ontario Vital Statistics)
- **Coverage:** All first names given to ≥5 babies in any single year, 1913–2023
- **Files:** `ontario_baby_names_female.csv`, `ontario_baby_names_male.csv`
- **Size:** ~177,000 rows (92,824 female + 84,246 male)
- **Key limitation:** Binary male/female classification only — no gender-neutral category

### Ontario Gazette Name Changes (2000–2024)
- **Source:** ontario.ca — "Notice of Change of Name" sections extracted from weekly PDF gazettes
- **Coverage:** All legal first-name changes published in the Ontario Gazette, Jan 2000 – Dec 2024
- **Files:** `data/raw/ontario_name_changes.csv`
- **Size:** 149,602 extracted records from 1,234 gazette issues
- **Fields captured:** old name (first + last), new name (first + last), gazette date, issue metadata

### How Records Are Linked

The gazette records are matched against the baby name data using **gender delta scoring** (see Methodology). The gazette does not record trans status, so trans name changes are inferred rather than observed directly.

---

## 3. Methodology

### 3.1 Gender Delta Scoring

For each name in the gazette, we compute the probability of female gender from the baby name dataset:

```
P(female | name) = total_female_count / (total_female_count + total_male_count)
```

The **gender delta** for a name change is:
```
gender_delta = P(female | new_name) - P(female | old_name)
```

- **+1.0** = changed from a name exclusively male in baby data to one exclusively female → likely MTF
- **−1.0** = changed from exclusively female to exclusively male → likely FTM
- **~0.0** = no gender shift (most name changes: divorce, immigration, etc.)

We use `|gender_delta| ≥ 0.7` as the "likely-trans" threshold, yielding **9,512 records** (13.2% of total).

### 3.2 Cross-Correlation Lag Analysis

For names appearing in both datasets across multiple years, we compute the cross-correlation between:
- **Gazette series:** annual relative frequency of the name appearing as a new name in gazette changes
- **Baby name series:** annual relative frequency of the name as a baby name

The lag at maximum correlation is interpreted as: if positive, gazette appearances of a name *precede* peaks in baby naming by that many years (i.e., the name change cohort is ahead of the trend).

Analysis was run on three populations:
1. All records (1,272 names with sufficient data)
2. Likely-trans subset (394 names)
3. Pre-2006 and post-2006 separately (see limitations)

### 3.3 Curve Score (Per-Record Trend Position)

A more direct metric: for each name change in year Y to name N, we compute:

```
before_freq = Σ rel_freq(N, y) for y in [Y−5, Y−1]
after_freq  = Σ rel_freq(N, y) for y in [Y+1, Y+5]
curve_score = (after_freq − before_freq) / (after_freq + before_freq)
```

Where `rel_freq(N, y) = count(N, y) / total_babies(y)` (normalised for population growth).

- **+1.0** = name was entirely absent before the change year, only appeared after → maximally ahead of the curve
- **−1.0** = name was absent after → name is fully past its peak, behind the curve
- **0.0** = equal baby name frequency before and after → right at the trend peak
- **null** = name has no baby data in the 10-year window (too rare to score)

Restricted to 2000–2018 (baby data runs to 2023; 2018+5=2023 gives a clean window).

### 3.4 Granger Causality

An aggregate time-series test: does the annual proportion of trans-coded name changes in the gazette predict future average baby name frequency changes? Tested at lags 1–5 years using Granger causality tests (statsmodels).

---

## 4. Findings

### 4.1 Population Overview

| Group | N records | N unique names |
|---|---|---|
| All gazette changes | 72,013 (scored) | — |
| Likely-trans (`\|δ\| ≥ 0.7`) | 9,512 | 2,530 |
| MTF (`δ ≥ +0.7`) | 4,541 | — |
| FTM (`δ ≤ −0.7`) | 4,972 | — |

Name changes grew dramatically over the period: from ~200 likely-trans records in 2000–2004 to ~2,000+ in 2020–2024, consistent with increased trans visibility and community. MTF initially outnumbered FTM but FTM has dominated since ~2015.

### 4.2 Lag Analysis — Primary Finding

Cross-correlation analysis on names with sufficient data (≥4 gazette appearances, ≥10 baby name years):

| Group | N names | Mean best lag | Interpretation |
|---|---|---|---|
| All gazette changes | 1,272 | **−0.30 years** | Gazette *lags* baby trends |
| Likely-trans (`\|δ\| ≥ 0.7`) | 394 | **+0.86 years** | Trans names *lead* baby trends |
| MTF (`δ ≥ +0.7`) | 201 | **+1.71 years** | Stronger apparent lead |
| FTM (`δ ≤ −0.7`) | 195 | **+0.78 years** | Moderate apparent lead |

The sign flip is striking: across all name changes, the gazette *follows* baby naming trends (people choose culturally current names). But in the trans-coded subset, the pattern reverses — those names appear in the gazette *before* they peak in baby data.

**Important caveat on the MTF result (see §5.2):** The +1.71y MTF lag is likely a statistical artifact. MTF trans women tend to choose names popular in their formative years (1960s–1980s female names like JESSICA, JENNIFER, MICHELLE). These names were already declining in baby data before 2000 and continued to decline throughout the study period. When two declining time series are cross-correlated with a slight timing offset, the result can look like a positive lag without any genuine predictive relationship.

### 4.3 MTF/FTM Difference — Not Statistically Significant

The difference between MTF (+1.71y) and FTM (+0.78y) mean lags is **not statistically significant** (Welch t-test: p=0.21; Mann-Whitney U: p=0.45). This means we cannot conclude that MTF and FTM trans people show different degrees of "trend-leading" behavior.

### 4.4 Granger Causality — Non-Significant

The aggregate time-series test (does gazette trans-rate predict average baby frequency?) shows **no significant Granger causality at any lag from 1–5 years** (all p > 0.22). There is no detectable macro-level causal signal in the aggregate time series.

This doesn't definitively falsify the hypothesis — the signal, if real, may only appear at the individual name level and average out across the full corpus.

### 4.5 Curve Scores — Trans People Are Behind the Curve

The curve score analysis gives a clearer and perhaps more surprising result:

| Group | N (2000–2018) | Mean score | p-value |
|---|---|---|---|
| All records | 31,109 | **−0.104** | <0.001 |
| Likely-trans | 5,147 | **−0.121** | <0.001 |
| MTF | 2,725 | **−0.137** | <0.001 |
| FTM | 2,422 | **−0.104** | <0.001 |
| Non-trans | 11,028 | **−0.100** | <0.001 |

**Every group scores negative** — on average, chosen names had *more* baby name frequency in the 5 years before the change than in the 5 years after. Everyone is choosing names that are past their peak more often than names on the rise. Trans people score slightly *more* negative than non-trans, not less.

The time trend is slight but directionally encouraging: the mean curve score for trans records improves by about +0.0024 per year over 2000–2018, suggesting the gap is narrowing — but this trend is not statistically significant (p=0.26).

**5-year chunk breakdown (trans mean curve score):**

| Period | Trans | MTF | FTM |
|---|---|---|---|
| 2000–04 | −0.123 | −0.145 | −0.081 |
| 2005–09 | −0.140 | −0.159 | −0.117 |
| 2010–14 | −0.132 | −0.142 | −0.120 |
| **2015–18** | **−0.095** | **−0.107** | **−0.084** |

The 2015–18 cohort shows the least negative scores, consistent with more trans people in recent years choosing contemporary names (OLIVER, KAI, NOAH for FTM; EMILY, CHLOE for MTF).

### 4.6 Most and Least Trend-Setting Names

**Most ahead-of-curve trans names** (mean curve score, n≥3):
JOAN (+1.0), JUNE (+0.88), LORI (+0.67), BO (+0.66), NOVA (+0.65), JULES (+0.62), MILO (+0.44), HENRY (+0.35)

**Most behind-curve trans names:**
SHELLY (−1.0), OLGA (−1.0), MEI (−1.0), SEYED (−1.0), KIMBERLEY (−0.93), KIM (−0.84), PAMELA (−0.78)

The ahead-of-curve names span an interesting range: some are vintage revival names (JOAN, JUNE, PEARL, SHEILA) that were becoming fashionable again after decades away; others are genuinely novel or gender-bending (BO, NOVA, JULES).

---

## 5. Limitations

### 5.1 Trans Opt-Out (2006+)
Since 2006, Ontario has allowed trans people to request non-publication of their name change in the Gazette. This creates **systematic underrepresentation of trans name changes in the 2006–2024 data**. The pre-2006 data is cleaner in this respect, but covers only 6 years and too few records (~600 likely-trans) for robust lag analysis.

This means our "likely-trans" filter is not pure — some post-2006 trans name changes were excluded from the Gazette entirely, while non-trans changes (divorce, immigration) are still published. The trans signal in post-2006 data is diluted.

### 5.2 The MTF Confound
The apparent MTF positive lag (+1.71y) is almost certainly a **statistical artifact**:
- MTF trans women predominantly choose female names that were popular in the 1960s–1980s (JESSICA, JENNIFER, MICHELLE, LINDA, CYNTHIA)
- These names were all declining monotonically in baby data throughout 2000–2024
- When a declining time series (gazette MTF frequency) is cross-correlated with another declining time series (baby name frequency) with a slight timing offset, it produces a spurious positive lag

The FTM signal (+0.78y) is less obviously artifactual — FTM men in recent years have chosen genuinely contemporary names (OLIVER, KAI, ALEX, NOAH) — but the MTF positive lag should not be interpreted as evidence that MTF trans women are "ahead of the curve."

### 5.3 Gender Delta Is a Coarse Proxy
The gender delta scoring has several weaknesses:
- **Binary classification:** Baby name data only distinguishes male/female — names classified as gender-neutral in culture score near 0.5 and may not trigger the filter
- **Gender-neutral name choices are invisible:** Trans people choosing names like ALEX, ROBIN, RIVER, or PHOENIX score low gender delta and are excluded from the trans-coded subset
- **Threshold is arbitrary:** The `|δ| ≥ 0.7` cutoff was chosen by inspection; different thresholds yield different sample sizes (0.5: ~18,000 records; 0.7: ~9,500; 0.9: ~5,000)
- **False positives:** Immigrants, divorce-related changes, and other non-trans changes with names that happen to have strong gender associations will score high delta

### 5.4 Geographic Scope
The data covers Ontario only. Canadian and American naming trends have historically been correlated but not identical. Results may not generalize to other regions.

### 5.5 PDF Parsing Fragility
The Gazette format changed substantially over 25 years. The scraper uses four regex patterns to handle different eras. Approximately 2 PDFs (~0.2%) are unreadable due to CID font encoding (requiring OCR to fix). The parser yield varies by year; 2004 has two known anomalous issues.

### 5.6 Sample Size and Statistical Power
- 394 names with sufficient data for lag analysis is not large
- The pre-2006 "natural experiment" (before opt-out) covers only ~600 likely-trans records — too few for reliable conclusions
- Granger causality is tested on only 24 annual observations (2000–2023), severely limiting power

---

## 6. Open Questions

1. **Is the positive lag real after controlling for name popularity trajectories?** A proper test would partial out the trend component of each time series before cross-correlating.

2. **What happens with gender-neutral names?** Tracking names in the 0.4–0.6 P(female) range might reveal a signal invisible to the current binary filter.

3. **Do specific name types show stronger signals?** Phonetic clusters, ethnic-origin groups, vintage revival names, invented names — do any subsets show cleaner predictive patterns?

4. **Comparison to US data?** The US Social Security Administration baby name database is freely available; if a US equivalent of the Ontario Gazette exists, a cross-national comparison would be illuminating.

5. **What would confirm the hypothesis cleanly?** The strongest test would be: for names first appearing in the gazette *before* they appear in the baby name data at all (true "discoveries"), do those names subsequently grow in baby frequency? A handful of such names exist in the data.

---

## 7. Summary

The hypothesis that trans name changes predict future baby naming trends finds **partial, tentative, and methodologically fragile support:**

- The cross-correlation lag *does* flip sign for the trans-coded subset (+0.86y lead vs −0.30y lag for all changes) — the direction is consistent with the hypothesis
- But the MTF component of that signal is likely artifactual (two declining series)
- The curve score analysis suggests trans people are on average *behind* the trend, not ahead of it — though the gap has narrowed since 2015
- Granger causality finds no macro-level signal
- The dataset is fundamentally limited by trans opt-out, binary gender coding, and moderate sample size

The most honest summary: *the data does not clearly falsify the hypothesis, but neither does it convincingly confirm it.* A stronger test would require a dataset without the opt-out confound and finer-grained gender metadata.

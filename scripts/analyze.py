#!/usr/bin/env python3
"""
Analyze whether name changes predict baby name trends.

This script tests the hypothesis that name choices in legal name changes
(as a proxy for trans name changes) are predictive of future baby naming trends.

KEY FEATURE: Gender-delta scoring
Uses baby name data to infer the "gender" of old and new names, then calculates
the gender shift. High |gender_delta| indicates likely trans name change.

Usage:
    python scripts/analyze.py \
        --name-changes data/raw/ontario_name_changes.csv \
        --baby-names-female data/raw/ontario_baby_names_female.csv \
        --baby-names-male data/raw/ontario_baby_names_male.csv \
        --output-dir data/processed/

Requirements:
    pip install pandas numpy scipy statsmodels matplotlib seaborn
"""

import argparse
from pathlib import Path
from typing import Optional
import warnings

import pandas as pd
import numpy as np
from scipy import stats
import matplotlib.pyplot as plt
import seaborn as sns

try:
    from statsmodels.tsa.stattools import grangercausalitytests
    HAS_STATSMODELS = True
except ImportError:
    HAS_STATSMODELS = False
    warnings.warn("statsmodels not installed. Granger causality tests will be skipped.")


# =============================================================================
# DATA LOADING
# =============================================================================

def load_name_changes(filepath: str) -> pd.DataFrame:
    """Load name change data."""
    df = pd.read_csv(filepath)
    df['year'] = pd.to_datetime(df['gazette_date']).dt.year
    df['new_first_name'] = df['new_first_name'].str.upper().str.strip()
    df['old_first_name'] = df['old_first_name'].str.upper().str.strip()
    return df


def load_baby_names(filepath: str) -> pd.DataFrame:
    """Load Ontario baby names data."""
    df = pd.read_csv(filepath)
    df.columns = df.columns.str.lower().str.strip()
    
    # Standardize column names (handle bilingual headers like "Name/Nom")
    rename_map = {}
    for col in df.columns:
        if any(s in col for s in ['name', 'nom', 'nombre']):
            rename_map[col] = 'first_name'
        elif any(s in col for s in ['frequency', 'count', 'freq']):
            rename_map[col] = 'count'
        elif any(s in col for s in ['year', 'année', 'anno']):
            rename_map[col] = 'year'
    df = df.rename(columns=rename_map)
    
    df['first_name'] = df['first_name'].str.upper().str.strip()
    return df


# =============================================================================
# GENDER INFERENCE
# =============================================================================

def build_gender_lookup(baby_female: pd.DataFrame, baby_male: pd.DataFrame) -> dict:
    """
    Build a name -> P(female) lookup table from baby name data.
    
    Returns dict mapping uppercase name to probability it's female (0-1).
    """
    # Aggregate total counts across all years
    f_col = 'first_name' if 'first_name' in baby_female.columns else 'name'
    m_col = 'first_name' if 'first_name' in baby_male.columns else 'name'
    count_col_f = 'count' if 'count' in baby_female.columns else 'frequency'
    count_col_m = 'count' if 'count' in baby_male.columns else 'frequency'
    
    female_totals = baby_female.groupby(baby_female[f_col].str.upper().str.strip())[count_col_f].sum()
    male_totals = baby_male.groupby(baby_male[m_col].str.upper().str.strip())[count_col_m].sum()
    
    all_names = set(female_totals.index) | set(male_totals.index)
    gender_lookup = {}
    
    for name in all_names:
        f_count = female_totals.get(name, 0)
        m_count = male_totals.get(name, 0)
        total = f_count + m_count
        gender_lookup[name] = f_count / total if total > 0 else 0.5
    
    return gender_lookup


def score_gender_delta(nc_df: pd.DataFrame, gender_lookup: dict) -> pd.DataFrame:
    """
    Add gender delta scores to name change dataframe.
    
    gender_delta = P(female | new_name) - P(female | old_name)
    
    Positive delta = shift toward female (likely MTF)
    Negative delta = shift toward male (likely FTM)
    """
    df = nc_df.copy()
    
    df['old_p_female'] = df['old_first_name'].map(lambda x: gender_lookup.get(x, 0.5))
    df['new_p_female'] = df['new_first_name'].map(lambda x: gender_lookup.get(x, 0.5))
    df['gender_delta'] = df['new_p_female'] - df['old_p_female']
    
    # Classify
    df['gender_change_type'] = 'none'
    df.loc[df['gender_delta'] > 0.5, 'gender_change_type'] = 'likely_mtf'
    df.loc[df['gender_delta'] < -0.5, 'gender_change_type'] = 'likely_ftm'
    df.loc[(df['gender_delta'].abs() > 0.1) & 
           (df['gender_delta'].abs() <= 0.5), 'gender_change_type'] = 'modest_shift'
    
    return df


def filter_likely_trans(nc_df: pd.DataFrame, threshold: float = 0.7) -> pd.DataFrame:
    """Filter to name changes with strong gender delta (likely trans)."""
    return nc_df[nc_df['gender_delta'].abs() >= threshold].copy()


# =============================================================================
# FREQUENCY CALCULATIONS
# =============================================================================

def calculate_name_frequencies(df: pd.DataFrame, name_col: str, year_col: str, 
                                count_col: Optional[str] = None) -> pd.DataFrame:
    """Calculate relative frequency of each name by year."""
    if count_col and count_col in df.columns:
        yearly = df.groupby([year_col, name_col])[count_col].sum().reset_index()
        yearly.columns = ['year', 'name', 'count']
    else:
        yearly = df.groupby([year_col, name_col]).size().reset_index()
        yearly.columns = ['year', 'name', 'count']
    
    yearly_totals = yearly.groupby('year')['count'].transform('sum')
    yearly['frequency'] = yearly['count'] / yearly_totals
    return yearly


# =============================================================================
# CROSS-CORRELATION ANALYSIS
# =============================================================================

def calculate_cross_correlation(series1: pd.Series, series2: pd.Series, 
                                 max_lag: int = 15) -> dict:
    """
    Calculate cross-correlation at various lags.
    Positive lag = series1 leads series2.
    """
    correlations = {}
    
    for lag in range(-max_lag, max_lag + 1):
        if lag > 0:
            s1 = series1.iloc[:-lag] if lag < len(series1) else pd.Series()
            s2 = series2.iloc[lag:] if lag < len(series2) else pd.Series()
        elif lag < 0:
            s1 = series1.iloc[-lag:] if -lag < len(series1) else pd.Series()
            s2 = series2.iloc[:lag] if lag < len(series2) else pd.Series()
        else:
            s1, s2 = series1, series2
        
        if len(s1) > 3 and len(s2) > 3:
            common_idx = s1.index.intersection(s2.index)
            if len(common_idx) > 3:
                corr, pval = stats.pearsonr(s1.loc[common_idx], s2.loc[common_idx])
                correlations[lag] = {'correlation': corr, 'pvalue': pval, 'n': len(common_idx)}
    
    return correlations


def analyze_name_trend(name: str, nc_yearly: pd.DataFrame, baby_yearly: pd.DataFrame,
                       max_lag: int = 10) -> Optional[dict]:
    """Analyze whether a name's frequency in name changes predicts baby name frequency."""
    nc_name = nc_yearly[nc_yearly['name'] == name].set_index('year')['frequency']
    baby_name = baby_yearly[baby_yearly['name'] == name].set_index('year')['frequency']
    
    if len(nc_name) < 5 or len(baby_name) < 5:
        return None
    
    correlations = calculate_cross_correlation(nc_name, baby_name, max_lag)
    if not correlations:
        return None
    
    best_lag = max(correlations.keys(), key=lambda k: correlations[k]['correlation'])
    
    return {
        'name': name,
        'best_lag': best_lag,
        'best_correlation': correlations[best_lag]['correlation'],
        'best_pvalue': correlations[best_lag]['pvalue'],
        'nc_years': len(nc_name),
        'baby_years': len(baby_name),
    }


# =============================================================================
# MAIN ANALYSES
# =============================================================================

def run_gender_delta_analysis(nc_df: pd.DataFrame, gender_lookup: dict,
                               output_dir: Path, trans_threshold: float = 0.7) -> pd.DataFrame:
    """Score all name changes by gender delta and output summary."""
    print("\n" + "="*60)
    print("GENDER DELTA ANALYSIS")
    print("="*60)

    nc_scored = score_gender_delta(nc_df, gender_lookup)

    print(f"\nTotal name changes: {len(nc_scored):,}")
    print(f"\nGender change type distribution:")
    print(nc_scored['gender_change_type'].value_counts())

    # Filter to likely trans at the primary threshold
    likely_trans = filter_likely_trans(nc_scored, threshold=trans_threshold)
    print(f"\nLikely trans (|delta| >= {trans_threshold}): {len(likely_trans):,} "
          f"({100*len(likely_trans)/len(nc_scored):.1f}%)")

    mtf = likely_trans[likely_trans['gender_delta'] > 0]
    ftm = likely_trans[likely_trans['gender_delta'] < 0]
    print(f"  Likely MTF: {len(mtf):,}")
    print(f"  Likely FTM: {len(ftm):,}")

    # Save scored data
    nc_scored.to_csv(output_dir / 'name_changes_scored.csv', index=False)
    likely_trans.to_csv(output_dir / 'likely_trans_name_changes.csv', index=False)
    mtf.to_csv(output_dir / 'likely_mtf_name_changes.csv', index=False)
    ftm.to_csv(output_dir / 'likely_ftm_name_changes.csv', index=False)

    # Plot gender delta distribution
    fig, ax = plt.subplots(figsize=(10, 6))
    nc_scored['gender_delta'].hist(bins=50, ax=ax, edgecolor='black', alpha=0.7)
    ax.axvline(x=trans_threshold, color='red', linestyle='--', label=f'Trans threshold (+{trans_threshold})')
    ax.axvline(x=-trans_threshold, color='red', linestyle='--', label=f'Trans threshold (-{trans_threshold})')
    ax.axvline(x=0, color='gray', linestyle='-', alpha=0.5)
    ax.set_xlabel('Gender Delta (+ = toward female, - = toward male)')
    ax.set_ylabel('Count')
    ax.set_title('Distribution of Gender Delta in Name Changes')
    ax.legend()
    plt.tight_layout()
    plt.savefig(output_dir / 'gender_delta_distribution.png', dpi=150)
    plt.close()
    print(f"\nGender delta plot saved to {output_dir / 'gender_delta_distribution.png'}")

    # Year breakdown
    print("\nLikely trans name changes by year:")
    yearly = likely_trans.groupby('year').size()
    print(yearly.to_string())

    return nc_scored


def plot_dose_response(dose_response: list[dict], output_dir: Path):
    """Plot threshold vs mean lag (dose-response curve)."""
    import matplotlib.pyplot as plt

    df = pd.DataFrame(dose_response).dropna(subset=['mean_lag'])
    if len(df) < 2:
        print("Not enough threshold points for dose-response plot.")
        return

    fig, ax1 = plt.subplots(figsize=(8, 5))
    ax2 = ax1.twinx()

    ax1.plot(df['threshold'], df['mean_lag'], 'o-', color='steelblue', linewidth=2, label='Mean lag (sig.)')
    ax1.axhline(0, color='gray', linestyle='--', alpha=0.5)
    ax1.set_xlabel('|Gender Delta| threshold')
    ax1.set_ylabel('Mean optimal lag (years)', color='steelblue')
    ax1.tick_params(axis='y', labelcolor='steelblue')

    ax2.bar(df['threshold'], df['n_sig'], alpha=0.3, color='orange', width=0.05, label='N significant names')
    ax2.set_ylabel('N significant names', color='orange')
    ax2.tick_params(axis='y', labelcolor='orange')

    ax1.set_title('Threshold Dose-Response: Gender Delta vs Mean Lag\n'
                  'If slope > 0, stronger gender shift → longer lead time (supports hypothesis)')
    fig.legend(loc='upper left', bbox_to_anchor=(0.1, 0.88))
    plt.tight_layout()
    plt.savefig(output_dir / 'dose_response.png', dpi=150)
    plt.close()
    print(f"Dose-response plot saved to {output_dir / 'dose_response.png'}")


def run_aggregate_analysis(nc_df: pd.DataFrame, baby_female: pd.DataFrame, 
                           baby_male: pd.DataFrame, output_dir: Path,
                           label: str = "all"):
    """Run cross-correlation analysis."""
    print(f"\n" + "="*60)
    print(f"CROSS-CORRELATION ANALYSIS ({label.upper()})")
    print("="*60)
    
    nc_yearly = calculate_name_frequencies(nc_df, 'new_first_name', 'year')

    # Combine male + female raw counts so each name has one frequency per year
    baby_combined = pd.concat([baby_female, baby_male], ignore_index=True)
    baby_all = calculate_name_frequencies(baby_combined, 'first_name', 'year', 'count')
    
    nc_names = set(nc_yearly['name'].unique())
    baby_names = set(baby_all['name'].unique())
    common_names = nc_names & baby_names
    
    print(f"\nNames in name changes: {len(nc_names):,}")
    print(f"Names in baby data: {len(baby_names):,}")
    print(f"Names in both: {len(common_names):,}")
    
    results = []
    for name in common_names:
        result = analyze_name_trend(name, nc_yearly, baby_all, max_lag=10)
        if result:
            results.append(result)
    
    if not results:
        print("No names had sufficient data.")
        return None
    
    results_df = pd.DataFrame(results)
    
    print(f"\nAnalyzed {len(results_df)} names")
    print(f"\nOptimal lag distribution:")
    print(results_df['best_lag'].value_counts().sort_index())
    
    sig = results_df[results_df['best_pvalue'] < 0.05]
    print(f"\nSignificant correlations (p<0.05): {len(sig)}")
    
    if len(sig) > 0:
        print(f"Mean lag (significant): {sig['best_lag'].mean():.2f}")
        print(f"Median lag (significant): {sig['best_lag'].median():.1f}")
        pos_lag = sig[sig['best_lag'] > 0]
        print(f"With positive lag (name changes lead): {len(pos_lag)} ({100*len(pos_lag)/len(sig):.1f}%)")
    
    results_df.to_csv(output_dir / f'correlation_results_{label}.csv', index=False)
    
    # Plot
    fig, ax = plt.subplots(figsize=(10, 6))
    results_df['best_lag'].hist(bins=range(-11, 12), ax=ax, edgecolor='black')
    ax.axvline(x=0, color='red', linestyle='--')
    ax.set_xlabel('Optimal Lag (years)')
    ax.set_ylabel('Number of Names')
    ax.set_title(f'Lag Distribution ({label})\nPositive = Name Changes Lead Baby Names')
    plt.tight_layout()
    plt.savefig(output_dir / f'lag_distribution_{label}.png', dpi=150)
    
    return results_df


def run_emerging_names_analysis(nc_df: pd.DataFrame, baby_female: pd.DataFrame,
                                baby_male: pd.DataFrame, output_dir: Path,
                                label: str = "all"):
    """Track whether names in name changes later increase in baby popularity."""
    print(f"\n" + "="*60)
    print(f"EMERGING NAMES ANALYSIS ({label.upper()})")
    print("="*60)
    
    nc_yearly = calculate_name_frequencies(nc_df, 'new_first_name', 'year')
    baby_combined = pd.concat([baby_female, baby_male], ignore_index=True)
    baby_all = calculate_name_frequencies(baby_combined, 'first_name', 'year', 'count')
    
    periods = [(2000, 2005), (2006, 2010), (2011, 2015), (2016, 2020)]
    emerging = []
    
    for start, end in periods:
        nc_period = nc_yearly[(nc_yearly['year'] >= start) & (nc_yearly['year'] <= end)]
        nc_names = set(nc_period['name'].unique())
        
        baby_during = baby_all[(baby_all['year'] >= start) & (baby_all['year'] <= end)]
        baby_after = baby_all[(baby_all['year'] > end) & (baby_all['year'] <= end + 10)]
        
        for name in nc_names:
            freq_during = baby_during[baby_during['name'] == name]['frequency'].mean()
            freq_after = baby_after[baby_after['name'] == name]['frequency'].mean()
            nc_count = len(nc_period[nc_period['name'] == name])
            
            if nc_count >= 2:
                emerging.append({
                    'name': name,
                    'period': f"{start}-{end}",
                    'nc_count': nc_count,
                    'baby_freq_during': freq_during if pd.notna(freq_during) else 0,
                    'baby_freq_after': freq_after if pd.notna(freq_after) else 0,
                })
    
    if not emerging:
        print("No data for emerging names analysis.")
        return None
    
    df = pd.DataFrame(emerging)
    df['freq_change'] = df['baby_freq_after'] - df['baby_freq_during']
    
    print(f"\nAnalyzed {len(df)} name-period combinations")
    print(f"Average frequency change: {df['freq_change'].mean():.6f}")
    
    increased = (df['freq_change'] > 0).sum()
    total = len(df[df['freq_change'].notna()])
    print(f"Names that increased: {increased}/{total} ({100*increased/total:.1f}%)")
    
    if len(df) > 10:
        t, p = stats.ttest_1samp(df['freq_change'].dropna(), 0)
        print(f"T-test (H0: mean=0): t={t:.3f}, p={p:.4f}")
    
    df.to_csv(output_dir / f'emerging_names_{label}.csv', index=False)
    return df


# =============================================================================
# GRANGER CAUSALITY
# =============================================================================

def run_aggregate_granger(nc_scored: pd.DataFrame, baby_female: pd.DataFrame,
                          baby_male: pd.DataFrame, output_dir: Path,
                          trans_threshold: float = 0.7, max_lag: int = 5):
    """
    Granger causality test on aggregate time series.

    Tests whether the yearly rate of trans name adoptions in the gazette
    Granger-causes the aggregate baby-name popularity of those same names.

    Saves results/granger_causality.csv with F-stat and p-value per lag.
    """
    if not HAS_STATSMODELS:
        print("\nSkipping Granger causality — statsmodels not available.")
        return

    from statsmodels.tsa.stattools import adfuller, grangercausalitytests

    print("\n" + "="*60)
    print("GRANGER CAUSALITY (aggregate time series)")
    print("="*60)

    likely_trans = filter_likely_trans(nc_scored, threshold=trans_threshold)
    trans_names = set(likely_trans['new_first_name'].unique())

    # Series A: trans adoption rate = likely-trans changes / all changes, by year
    gazette_total = nc_scored.groupby('year').size()
    gazette_trans = likely_trans.groupby('year').size()
    gazette_rate = (gazette_trans / gazette_total).rename('gazette_trans_rate')

    # Series B: aggregate baby popularity of those same names, by year
    baby_combined = pd.concat([baby_female, baby_male], ignore_index=True)
    baby_trans = baby_combined[baby_combined['first_name'].isin(trans_names)]
    baby_total_by_year = baby_combined.groupby('year')['count'].sum()
    baby_trans_by_year = baby_trans.groupby('year')['count'].sum()
    baby_rate = (baby_trans_by_year / baby_total_by_year).rename('baby_trans_freq')

    # Align years
    combined = pd.concat([gazette_rate, baby_rate], axis=1).dropna()
    print(f"  Years with both series: {len(combined)} ({combined.index.min()}-{combined.index.max()})")

    # Stationarity check + differencing
    def is_stationary(series, alpha=0.05):
        result = adfuller(series.dropna(), autolag='AIC')
        return result[1] < alpha  # p-value < alpha → stationary

    gz = combined['gazette_trans_rate']
    by = combined['baby_trans_freq']

    gz_stat = is_stationary(gz)
    by_stat = is_stationary(by)
    print(f"  ADF stationarity — gazette: {'yes' if gz_stat else 'no'}, baby: {'yes' if by_stat else 'no'}")

    if not gz_stat:
        gz = gz.diff().dropna()
    if not by_stat:
        by = by.diff().dropna()

    # Align after differencing; limit max_lag to what statsmodels allows
    idx = gz.index.intersection(by.index)
    data = np.column_stack([by.loc[idx].values, gz.loc[idx].values])  # [y, x]: gazette -> baby?
    nobs = data.shape[0]
    # statsmodels requires nobs > 3*(maxlag+1) approximately; use conservative formula
    max_lag = min(max_lag, max(1, (nobs - 2) // 3))
    print(f"  Effective obs after differencing: {nobs}, using max_lag={max_lag}")

    if nobs < 8:
        print("  Not enough data after differencing for Granger test.")
        return

    try:
        gc_results = grangercausalitytests(data, maxlag=max_lag, verbose=False)
    except Exception as e:
        print(f"  Granger test failed: {e}")
        return

    rows = []
    for lag, res in gc_results.items():
        f_stat = res[0]['ssr_ftest'][0]
        p_val  = res[0]['ssr_ftest'][1]
        rows.append({'lag': lag, 'f_stat': round(f_stat, 4), 'p_value': round(p_val, 4),
                     'significant': p_val < 0.05})

    results_df = pd.DataFrame(rows)
    results_df.to_csv(output_dir / 'granger_causality.csv', index=False)

    print(f"\n  Lag  F-stat   p-value  sig?")
    print(f"  {'-'*35}")
    for _, row in results_df.iterrows():
        sig = '***' if row['p_value'] < 0.05 else ''
        print(f"  {int(row['lag']):>3}  {row['f_stat']:>7.3f}  {row['p_value']:>7.4f}  {sig}")
    print(f"\n  Saved -> {output_dir / 'granger_causality.csv'}")


# =============================================================================
# CURVE SCORE  (per-record "ahead/behind trend" metric)
# =============================================================================

def build_baby_rel_freq(baby_female: pd.DataFrame, baby_male: pd.DataFrame) -> pd.DataFrame:
    """
    Build a (first_name, year) → relative_frequency lookup table.

    Relative frequency = name_count / total_babies_that_year, summed across
    male and female files.  Returns a DataFrame with columns [first_name, year, rel_freq].
    """
    baby = pd.concat([baby_female, baby_male], ignore_index=True)
    year_totals = baby.groupby('year')['count'].sum()
    baby = baby.copy()
    baby['rel_freq'] = baby['count'] / baby['year'].map(year_totals)
    # Sum male+female rel_freq for the same name+year
    lookup = (baby.groupby(['first_name', 'year'])['rel_freq']
                  .sum()
                  .reset_index())
    return lookup


def compute_curve_scores(nc_scored: pd.DataFrame,
                         baby_female: pd.DataFrame,
                         baby_male: pd.DataFrame,
                         output_dir: Path,
                         window: int = 5,
                         year_min: int = 2000,
                         year_max: int = 2018) -> pd.DataFrame:
    """
    Assign each name-change record a "curve score" measuring whether the chosen
    name was rising (ahead of trend) or falling (behind trend) at the time of change.

    For a record changing TO name N in year Y:
        before_freq = sum of rel_freq(N, y) for y in [Y-window, Y-1]
        after_freq  = sum of rel_freq(N, y) for y in [Y+1, Y+window]
        curve_score = (after_freq - before_freq) / (after_freq + before_freq)

    Score ranges from -1 (fully behind curve) to +1 (fully ahead of curve).
    Records where the name has no baby data in the window get score = NaN.

    Restricts to year_min..year_max so both before and after windows are fully
    covered by baby name data (which runs to 2023; year_max=2018 → 2018+5=2023).

    Saves results/curve_scores.csv and prints a summary report.
    Returns the scored DataFrame.
    """
    print("\n" + "="*60)
    print("CURVE SCORE ANALYSIS (per-record ahead/behind trend)")
    print("="*60)

    # --- build lookup ---
    lookup = build_baby_rel_freq(baby_female, baby_male)
    # Pivot to wide: index=first_name, columns=year, values=rel_freq
    lookup_wide = (lookup.pivot_table(index='first_name', columns='year',
                                      values='rel_freq', aggfunc='sum', fill_value=0.0))
    all_years = set(lookup_wide.columns)
    print(f"  Baby name lookup: {len(lookup_wide):,} unique names, "
          f"years {min(all_years)}-{max(all_years)}")

    # --- restrict records ---
    df = nc_scored[(nc_scored['year'] >= year_min) &
                   (nc_scored['year'] <= year_max)].copy()
    print(f"  Records in {year_min}-{year_max}: {len(df):,}")

    # --- vectorised window sums via merges ---
    # For each offset k, merge in the baby rel_freq for (name, year+k)
    before_cols = []
    after_cols  = []
    for k in list(range(-window, 0)) + list(range(1, window + 1)):
        col = f'_rf_{k:+d}'
        df[col] = df['year'] + k  # target baby-name year
        # merge lookup: (first_name, target_year) → rel_freq
        tmp = lookup.rename(columns={'year': col, 'rel_freq': f'_v{k:+d}'})
        df = df.merge(tmp, left_on=['new_first_name', col], right_on=['first_name', col],
                      how='left', suffixes=('', '_dup'))
        # drop duplicate first_name col introduced by merge
        if 'first_name' in df.columns:
            df = df.drop(columns=['first_name'])
        df[f'_v{k:+d}'] = df[f'_v{k:+d}'].fillna(0.0)
        df = df.drop(columns=[col])
        if k < 0:
            before_cols.append(f'_v{k:+d}')
        else:
            after_cols.append(f'_v{k:+d}')

    df['before_freq'] = df[before_cols].sum(axis=1)
    df['after_freq']  = df[after_cols].sum(axis=1)
    total = df['before_freq'] + df['after_freq']

    df['curve_score'] = np.where(
        total > 0,
        (df['after_freq'] - df['before_freq']) / total,
        np.nan
    )

    # Drop the per-offset value columns
    df = df.drop(columns=before_cols + after_cols)

    scored = df[['old_first_name', 'new_first_name', 'gazette_date', 'year',
                 'gender_delta', 'before_freq', 'after_freq', 'curve_score']].copy()
    scored.to_csv(output_dir / 'curve_scores.csv', index=False)

    # --- summary stats ---
    valid = scored.dropna(subset=['curve_score'])
    trans = valid[valid['gender_delta'].abs() >= 0.7]
    mtf   = valid[valid['gender_delta'] >= 0.7]
    ftm   = valid[valid['gender_delta'] <= -0.7]
    non_t = valid[valid['gender_delta'].abs() < 0.1]

    def _summary(label, sub):
        if len(sub) < 5:
            print(f"  {label:35s}  n={len(sub):>5}  (too few)")
            return
        m = sub['curve_score'].mean()
        t, p = stats.ttest_1samp(sub['curve_score'], 0)
        sig = '***' if p < 0.001 else '**' if p < 0.01 else '*' if p < 0.05 else ''
        print(f"  {label:35s}  n={len(sub):>5}  mean={m:+.3f}  p={p:.4f} {sig}")

    print(f"\n  Curve score summary (window={window}y, records {year_min}-{year_max}):")
    print(f"  {'Group':35s}  {'n':>6}  {'mean':>8}  p-value")
    print(f"  {'-'*65}")
    _summary("All records",          valid)
    _summary("Likely-trans |d|>=0.7", trans)
    _summary("  MTF (d>=+0.7)",       mtf)
    _summary("  FTM (d<=-0.7)",       ftm)
    _summary("Non-trans |d|<0.1",    non_t)

    # --- by 5-year chunk ---
    print(f"\n  By 5-year chunk:")
    chunks = [(2000,2004,'2000-04'), (2005,2009,'2005-09'),
              (2010,2014,'2010-14'), (2015,2018,'2015-18')]
    for y0, y1, lbl in chunks:
        chunk_t = trans[(trans['year'] >= y0) & (trans['year'] <= y1)]
        chunk_m = mtf  [(mtf  ['year'] >= y0) & (mtf  ['year'] <= y1)]
        chunk_f = ftm  [(ftm  ['year'] >= y0) & (ftm  ['year'] <= y1)]
        def _chunk_mean(s):
            return f"{s['curve_score'].mean():+.3f}" if len(s) >= 5 else "  n/a"
        print(f"  {lbl}  trans={_chunk_mean(chunk_t)}  MTF={_chunk_mean(chunk_m)}  FTM={_chunk_mean(chunk_f)}")

    # --- time trend ---
    yearly = trans.groupby('year')['curve_score'].mean().reset_index()
    if len(yearly) >= 5:
        slope, intercept, r, p_trend, _ = stats.linregress(yearly['year'], yearly['curve_score'])
        direction = "INCREASING" if slope > 0 else "DECREASING"
        print(f"\n  Time trend (likely-trans, {year_min}-{year_max}):")
        print(f"  slope={slope:+.4f}/yr  r={r:.3f}  p={p_trend:.4f}")
        print(f"  -> Curve scores are {direction} over time "
              f"({'more' if slope > 0 else 'less'} trend-setting in recent years)")

    # --- top/bottom names by mean curve score in trans set ---
    name_scores = (trans.groupby('new_first_name')['curve_score']
                       .agg(['mean', 'count'])
                       .query('count >= 3')
                       .sort_values('mean', ascending=False))
    print(f"\n  Most AHEAD of curve (trans, n>=3 records):")
    for name, row in name_scores.head(10).iterrows():
        print(f"    {name:14s}  mean={row['mean']:+.3f}  n={int(row['count'])}")
    print(f"\n  Most BEHIND curve (trans, n>=3 records):")
    for name, row in name_scores.tail(10).iterrows():
        print(f"    {name:14s}  mean={row['mean']:+.3f}  n={int(row['count'])}")

    # --- write text report ---
    _write_curve_report(valid, trans, mtf, ftm, non_t, yearly, name_scores,
                        slope if len(yearly) >= 5 else None,
                        p_trend if len(yearly) >= 5 else None,
                        output_dir, window, year_min, year_max)

    print(f"\n  Saved -> {output_dir / 'curve_scores.csv'}")
    print(f"  Saved -> {output_dir / 'curve_score_report.txt'}")
    return scored


def _write_curve_report(valid, trans, mtf, ftm, non_t, yearly, name_scores,
                        slope, p_trend, output_dir, window, year_min, year_max):
    """Write human-readable curve score report."""
    from scipy import stats as _stats
    lines = []
    lines.append("CURVE SCORE REPORT")
    lines.append("=" * 60)
    lines.append(f"Window: +/-{window} years around each name change")
    lines.append(f"Period: {year_min}-{year_max} (full window guaranteed)")
    lines.append(f"Score: +1 = maximally ahead of trend, -1 = maximally behind")
    lines.append("")
    lines.append("GROUP MEANS")
    lines.append("-" * 40)

    def _fmt(label, sub):
        if len(sub) < 5:
            return f"{label:35s}  n={len(sub):>5}  (insufficient data)"
        m = sub['curve_score'].mean()
        md = sub['curve_score'].median()
        t, p = _stats.ttest_1samp(sub['curve_score'], 0)
        sig = '***' if p < 0.001 else '**' if p < 0.01 else '*' if p < 0.05 else 'ns'
        return f"{label:35s}  n={len(sub):>5}  mean={m:+.3f}  median={md:+.3f}  p={p:.4f} ({sig})"

    lines.append(_fmt("All records",           valid))
    lines.append(_fmt("Likely-trans |d|>=0.7", trans))
    lines.append(_fmt("  MTF (d>=+0.7)",        mtf))
    lines.append(_fmt("  FTM (d<=-0.7)",        ftm))
    lines.append(_fmt("Non-trans |d|<0.1",     non_t))
    lines.append("")
    lines.append("TIME TREND (likely-trans)")
    lines.append("-" * 40)
    if slope is not None:
        direction = "increasing" if slope > 0 else "decreasing"
        lines.append(f"Linear slope: {slope:+.4f} per year  (p={p_trend:.4f})")
        lines.append(f"Interpretation: Trans name choices are {direction} in 'ahead-of-curve'")
        lines.append(f"score over {year_min}-{year_max}, suggesting trans people are becoming")
        lines.append(f"{'MORE' if slope > 0 else 'LESS'} trend-setting over time.")
    lines.append("")
    lines.append("5-YEAR CHUNK BREAKDOWN (likely-trans mean curve score)")
    lines.append("-" * 40)
    chunks = [(2000,2004,'2000-04'), (2005,2009,'2005-09'),
              (2010,2014,'2010-14'), (2015,2018,'2015-18')]
    for y0, y1, lbl in chunks:
        chunk_t = trans[(trans['year'] >= y0) & (trans['year'] <= y1)]
        chunk_m = mtf  [(mtf  ['year'] >= y0) & (mtf  ['year'] <= y1)]
        chunk_f = ftm  [(ftm  ['year'] >= y0) & (ftm  ['year'] <= y1)]
        def _m(s): return f"{s['curve_score'].mean():+.3f}" if len(s)>=5 else "n/a"
        lines.append(f"{lbl}:  trans={_m(chunk_t)}  MTF={_m(chunk_m)}  FTM={_m(chunk_f)}"
                     f"  (n_trans={len(chunk_t)}, n_mtf={len(chunk_m)}, n_ftm={len(chunk_f)})")
    lines.append("")
    lines.append("TOP 15 MOST AHEAD-OF-CURVE NAMES (trans set, n>=3)")
    lines.append("-" * 40)
    for name, row in name_scores.head(15).iterrows():
        lines.append(f"  {name:14s}  mean={row['mean']:+.3f}  n={int(row['count'])}")
    lines.append("")
    lines.append("TOP 15 MOST BEHIND-CURVE NAMES (trans set, n>=3)")
    lines.append("-" * 40)
    for name, row in name_scores.tail(15).iterrows():
        lines.append(f"  {name:14s}  mean={row['mean']:+.3f}  n={int(row['count'])}")

    with open(output_dir / 'curve_score_report.txt', 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description='Analyze name change → baby name trends')
    parser.add_argument('--name-changes', '-n', required=True, help='Name changes CSV')
    parser.add_argument('--baby-names-female', '-f', required=True, help='Female baby names CSV')
    parser.add_argument('--baby-names-male', '-m', required=True, help='Male baby names CSV')
    parser.add_argument('--output-dir', '-o', default='data/processed', help='Output directory')
    parser.add_argument('--trans-threshold', type=float, default=0.7,
                        help='Gender delta threshold for likely-trans filter')
    parser.add_argument('--thresholds', default='0.2,0.5,0.7',
                        help='Comma-separated thresholds for dose-response analysis')
    args = parser.parse_args()
    
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)
    
    # Load data
    print("Loading data...")
    nc_df = load_name_changes(args.name_changes)
    baby_female = load_baby_names(args.baby_names_female)
    baby_male = load_baby_names(args.baby_names_male)
    
    nc_df = nc_df[nc_df['old_first_name'] != nc_df['new_first_name']]

    print(f"Name changes (first name changed): {len(nc_df):,}")
    print(f"Baby names (F): {len(baby_female):,}")
    print(f"Baby names (M): {len(baby_male):,}")
    print(f"NC years: {nc_df['year'].min()}-{nc_df['year'].max()}")
    
    # Build gender lookup
    print("\nBuilding gender lookup table...")
    gender_lookup = build_gender_lookup(baby_female, baby_male)
    print(f"Names in lookup: {len(gender_lookup):,}")
    
    # Score gender delta
    nc_scored = run_gender_delta_analysis(nc_df, gender_lookup, output_dir,
                                          trans_threshold=args.trans_threshold)

    # Filter to likely trans at primary threshold
    likely_trans = filter_likely_trans(nc_scored, threshold=args.trans_threshold)

    # Run analyses on ALL name changes
    run_aggregate_analysis(nc_scored, baby_female, baby_male, output_dir, label="all")
    run_emerging_names_analysis(nc_scored, baby_female, baby_male, output_dir, label="all")

    # Run analyses on LIKELY TRANS subset
    if len(likely_trans) >= 100:
        run_aggregate_analysis(likely_trans, baby_female, baby_male, output_dir, label="likely_trans")
        run_emerging_names_analysis(likely_trans, baby_female, baby_male, output_dir, label="likely_trans")
    else:
        print(f"\nSkipping likely-trans analysis (only {len(likely_trans)} records)")

    # MTF and FTM separate analyses
    mtf = nc_scored[nc_scored['gender_delta'] >= args.trans_threshold]
    ftm = nc_scored[nc_scored['gender_delta'] <= -args.trans_threshold]
    mtf_results, ftm_results = None, None
    print(f"\nRunning MTF analysis ({len(mtf):,} records)...")
    if len(mtf) >= 100:
        mtf_results = run_aggregate_analysis(mtf, baby_female, baby_male, output_dir, label="mtf")
    print(f"Running FTM analysis ({len(ftm):,} records)...")
    if len(ftm) >= 100:
        ftm_results = run_aggregate_analysis(ftm, baby_female, baby_male, output_dir, label="ftm")

    # MTF vs FTM lag comparison (two-sample test)
    if mtf_results is not None and ftm_results is not None:
        mtf_sig = mtf_results[mtf_results['best_pvalue'] < 0.05]['best_lag']
        ftm_sig = ftm_results[ftm_results['best_pvalue'] < 0.05]['best_lag']
        print("\n" + "="*60)
        print("MTF vs FTM LAG COMPARISON")
        print("="*60)
        print(f"  MTF significant names: {len(mtf_sig)}, mean lag={mtf_sig.mean():.2f}")
        print(f"  FTM significant names: {len(ftm_sig)}, mean lag={ftm_sig.mean():.2f}")
        if len(mtf_sig) >= 5 and len(ftm_sig) >= 5:
            t, p = stats.ttest_ind(mtf_sig, ftm_sig, equal_var=False)
            u, pu = stats.mannwhitneyu(mtf_sig, ftm_sig, alternative='two-sided')
            print(f"  Welch t-test:      t={t:.3f}, p={p:.4f}")
            print(f"  Mann-Whitney U:    U={u:.0f}, p={pu:.4f}")
            with open(output_dir / 'mtf_ftm_ttest.txt', 'w') as f:
                f.write(f"MTF vs FTM Lag Comparison\n{'='*40}\n")
                f.write(f"MTF (n={len(mtf_sig)}): mean lag = {mtf_sig.mean():.3f}\n")
                f.write(f"FTM (n={len(ftm_sig)}): mean lag = {ftm_sig.mean():.3f}\n\n")
                f.write(f"Welch t-test: t={t:.4f}, p={p:.4f}\n")
                f.write(f"Mann-Whitney: U={u:.0f}, p={pu:.4f}\n")
                f.write(f"\nInterpretation: p<0.05 means MTF and FTM show statistically\n"
                        f"different lead times, suggesting gender-direction matters.\n")

    # Pre-2006 analysis (before trans opt-out)
    pre_2006 = nc_scored[nc_scored['year'] < 2006]
    post_2006 = nc_scored[nc_scored['year'] >= 2006]
    if len(pre_2006) >= 100:
        print("\n" + "="*60)
        print("PRE-2006 ANALYSIS (before trans opt-out)")
        print("="*60)
        run_aggregate_analysis(pre_2006, baby_female, baby_male, output_dir, label="pre2006")
    if len(post_2006) >= 100:
        print("\n" + "="*60)
        print("POST-2006 ANALYSIS (after trans opt-out)")
        print("="*60)
        run_aggregate_analysis(post_2006, baby_female, baby_male, output_dir, label="post2006")

    # Threshold dose-response: run at each threshold, collect mean lag
    thresholds = [float(t) for t in args.thresholds.split(',')]
    print("\n" + "="*60)
    print("THRESHOLD DOSE-RESPONSE ANALYSIS")
    print("="*60)
    dose_response = []
    for thresh in thresholds:
        subset = filter_likely_trans(nc_scored, threshold=thresh)
        print(f"\n  threshold={thresh}: {len(subset):,} records")
        if len(subset) >= 100:
            result = run_aggregate_analysis(subset, baby_female, baby_male, output_dir,
                                            label=f"thresh_{thresh:.1f}")
            if result is not None:
                sig = result[result['best_pvalue'] < 0.05]
                mean_lag = sig['best_lag'].mean() if len(sig) > 0 else None
                dose_response.append({
                    'threshold': thresh,
                    'mean_lag': mean_lag,
                    'n_sig': len(sig),
                    'n_total': len(result),
                })
    if dose_response:
        plot_dose_response(dose_response, output_dir)

    # Aggregate Granger causality test
    run_aggregate_granger(nc_scored, baby_female, baby_male, output_dir,
                          trans_threshold=args.trans_threshold)

    # Per-record curve score analysis
    compute_curve_scores(nc_scored, baby_female, baby_male, output_dir)

    print("\n" + "="*60)
    print("COMPLETE")
    print("="*60)
    print(f"Results in: {output_dir}/")


if __name__ == '__main__':
    main()
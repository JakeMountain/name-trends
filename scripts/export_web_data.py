#!/usr/bin/env python3
"""
export_web_data.py

Reads analysis outputs from data/raw/ and data/processed/, exports compact
JSON files for the web app (app/data/).

Usage:
    python scripts/export_web_data.py \
        --raw-dir data/raw \
        --processed-dir data/processed \
        --output-dir app/data

Privacy: old first names are never written to any output file.
"""

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats


def load_baby_names(female_path: Path, male_path: Path) -> pd.DataFrame:
    dfs = []
    for path, gender in [(female_path, 'F'), (male_path, 'M')]:
        df = pd.read_csv(path)
        # Normalise column names (bilingual headers possible)
        df.columns = [c.strip().lower() for c in df.columns]
        name_col = next(c for c in df.columns if any(k in c for k in ('name', 'nom', 'first')))
        year_col = next(c for c in df.columns if any(k in c for k in ('year', 'ann')))
        freq_col = next(c for c in df.columns if any(k in c for k in ('freq', 'count')))
        df = df.rename(columns={name_col: 'name', year_col: 'year', freq_col: 'count'})
        df['gender'] = gender
        dfs.append(df[['name', 'year', 'count', 'gender']])
    baby = pd.concat(dfs, ignore_index=True)
    baby['name'] = baby['name'].str.upper().str.strip()
    return baby


def export_summary(processed_dir: Path, out_path: Path):
    print("  Exporting summary.json...")

    # Curve score report
    report = (processed_dir / 'curve_score_report.txt').read_text()

    def extract(label, text):
        for line in text.splitlines():
            if label in line:
                parts = line.split('mean=')
                if len(parts) > 1:
                    try:
                        return float(parts[1].split()[0])
                    except (ValueError, IndexError):
                        pass
        return None

    # Correlation results
    corr_all = pd.read_csv(processed_dir / 'correlation_results_all.csv')
    corr_trans = pd.read_csv(processed_dir / 'correlation_results_likely_trans.csv')

    # Name change counts
    scored = pd.read_csv(processed_dir / 'name_changes_scored.csv')
    trans = scored[scored['gender_delta'].abs() >= 0.7]
    mtf = scored[scored['gender_delta'] >= 0.7]
    ftm = scored[scored['gender_delta'] <= -0.7]

    # Curve scores for group means
    cs = pd.read_csv(processed_dir / 'curve_scores.csv').dropna(subset=['curve_score'])
    cs_trans = cs[cs['gender_delta'].abs() >= 0.7]
    cs_mtf   = cs[cs['gender_delta'] >= 0.7]
    cs_ftm   = cs[cs['gender_delta'] <= -0.7]
    cs_non   = cs[cs['gender_delta'].abs() < 0.1]

    # 5-year chunks for trans
    chunks = []
    for label, lo, hi in [('2000–04',2000,2004),('2005–09',2005,2009),
                           ('2010–14',2010,2014),('2015–18',2015,2018)]:
        t = cs_trans[(cs_trans['year']>=lo)&(cs_trans['year']<=hi)]
        m = cs_mtf[(cs_mtf['year']>=lo)&(cs_mtf['year']<=hi)]
        f = cs_ftm[(cs_ftm['year']>=lo)&(cs_ftm['year']<=hi)]
        chunks.append({
            'period': label,
            'trans': round(t['curve_score'].mean(), 3) if len(t) else None,
            'mtf':   round(m['curve_score'].mean(), 3) if len(m) else None,
            'ftm':   round(f['curve_score'].mean(), 3) if len(f) else None,
            'n': int(len(t))
        })

    # Top/bottom trans names by curve score (n>=3)
    cs_trans_named = cs_trans.groupby('new_first_name')['curve_score'].agg(['mean','count'])
    cs_trans_named = cs_trans_named[cs_trans_named['count'] >= 3]
    top_ahead = cs_trans_named.nlargest(10, 'mean').index.tolist()
    top_behind = cs_trans_named.nsmallest(10, 'mean').index.tolist()

    summary = {
        'total_scored': int(len(scored)),
        'trans_records': int(len(trans)),
        'mtf_records': int(len(mtf)),
        'ftm_records': int(len(ftm)),
        'scrape_years': '2000–2024',
        'gazette_issues': 1234,
        'baby_name_years': '1913–2023',
        'mean_lag_all': round(float(corr_all['best_lag'].mean()), 3),
        'mean_lag_trans': round(float(corr_trans['best_lag'].mean()), 3),
        'mean_curve_all':   round(float(cs['curve_score'].mean()), 3),
        'mean_curve_trans': round(float(cs_trans['curve_score'].mean()), 3),
        'mean_curve_mtf':   round(float(cs_mtf['curve_score'].mean()), 3),
        'mean_curve_ftm':   round(float(cs_ftm['curve_score'].mean()), 3),
        'mean_curve_nontrans': round(float(cs_non['curve_score'].mean()), 3),
        'chunk_breakdown': chunks,
        'top_ahead_names': top_ahead,
        'top_behind_names': top_behind,
    }

    # Add MTF/FTM lag from separate correlation files
    try:
        corr_mtf = pd.read_csv(processed_dir / 'correlation_results_mtf.csv')
        corr_ftm = pd.read_csv(processed_dir / 'correlation_results_ftm.csv')
        summary['mean_lag_mtf'] = round(float(corr_mtf['best_lag'].mean()), 3)
        summary['mean_lag_ftm'] = round(float(corr_ftm['best_lag'].mean()), 3)
    except FileNotFoundError:
        pass

    out_path.write_text(json.dumps(summary, indent=2))
    print(f"    -> {out_path} ({out_path.stat().st_size//1024} KB)")


def compute_gender_map(baby: pd.DataFrame) -> dict:
    """Return {name: 'F'/'M'/'N'} based on female fraction in baby name data."""
    totals = baby.groupby(['name', 'gender'])['count'].sum().unstack(fill_value=0)
    female = totals.get('F', pd.Series(0, index=totals.index))
    male   = totals.get('M', pd.Series(0, index=totals.index))
    total  = (female + male).clip(lower=1)
    female_ratio = female / total
    result = {}
    for name in female_ratio.index:
        r = female_ratio[name]
        result[name] = 'F' if r >= 0.6 else ('M' if r <= 0.4 else 'N')
    return result


def export_baby_names(baby: pd.DataFrame, out_path: Path, min_count: int = 3):
    """Export {name: [[year, rel_freq], ...]} for names with >=min_count in any year."""
    print("  Exporting baby_names.json...")

    year_totals = baby.groupby('year')['count'].sum()
    baby = baby.copy()
    baby['rel_freq'] = baby['count'] / baby['year'].map(year_totals)

    # Aggregate male+female
    agg = baby.groupby(['name', 'year'])['rel_freq'].sum().reset_index()

    # Keep only names with >=min_count appearances in some year
    max_per_name = baby.groupby('name')['count'].max()
    keep = max_per_name[max_per_name >= min_count].index
    agg = agg[agg['name'].isin(keep)]

    result = {}
    for name, grp in agg.groupby('name'):
        grp = grp.sort_values('year')
        result[name] = [[int(r['year']), round(float(r['rel_freq']), 7)]
                        for _, r in grp.iterrows()]

    out_path.write_text(json.dumps(result))
    size_mb = out_path.stat().st_size / 1_000_000
    print(f"    -> {out_path} ({size_mb:.1f} MB, {len(result):,} names)")


def export_name_changes(processed_dir: Path, out_path: Path):
    """Export privacy-safe records: new_first_name, year, gender_delta, curve_score only."""
    print("  Exporting name_changes.json...")

    scored = pd.read_csv(processed_dir / 'name_changes_scored.csv')
    cs = pd.read_csv(processed_dir / 'curve_scores.csv')[
        ['new_first_name', 'gazette_date', 'year', 'gender_delta', 'curve_score']
    ]

    # The scored file has all records; curve_scores has 2000-2018 subset with scores
    # Merge to get curve_score on the scored set; others get null
    cs_lookup = cs.set_index(['new_first_name', 'gazette_date'])['curve_score'].to_dict()

    records = []
    for _, row in scored.iterrows():
        key = (row['new_first_name'], row['gazette_date'])
        cs_val = cs_lookup.get(key, None)
        if cs_val is not None and (math.isnan(cs_val) if isinstance(cs_val, float) else False):
            cs_val = None
        records.append({
            'n': str(row['new_first_name']),
            'y': int(row['year']),
            'd': round(float(row['gender_delta']), 3),
            'cs': round(float(cs_val), 4) if cs_val is not None else None
        })

    out_path.write_text(json.dumps(records))
    size_mb = out_path.stat().st_size / 1_000_000
    print(f"    -> {out_path} ({size_mb:.1f} MB, {len(records):,} records)")


def export_correlation(processed_dir: Path, out_path: Path):
    """Export correlation results with trans flag and direction."""
    print("  Exporting correlation.json...")

    corr_all = pd.read_csv(processed_dir / 'correlation_results_all.csv')
    corr_trans = pd.read_csv(processed_dir / 'correlation_results_likely_trans.csv')
    trans_names = set(corr_trans['name'])

    # Direction: load scored to get mean delta per name
    scored = pd.read_csv(processed_dir / 'name_changes_scored.csv')
    mean_delta = scored.groupby('new_first_name')['gender_delta'].mean()

    records = []
    for _, row in corr_all.iterrows():
        name = row['name']
        is_trans = name in trans_names
        delta = mean_delta.get(name, 0.0)
        if delta >= 0.7:
            direction = 'MTF'
        elif delta <= -0.7:
            direction = 'FTM'
        else:
            direction = 'unclear'
        records.append({
            'name': name,
            'lag': int(row['best_lag']),
            'r': round(float(row['best_correlation']), 4),
            'p': round(float(row['best_pvalue']), 5),
            'is_trans': is_trans,
            'dir': direction,
            'mean_delta': round(float(delta), 3),
        })

    out_path.write_text(json.dumps(records))
    print(f"    -> {out_path} ({out_path.stat().st_size//1024} KB, {len(records)} names)")


def export_curve_summary(processed_dir: Path, out_path: Path, gender_map: dict):
    """Export per-name curve score summary for Browse Names tab."""
    print("  Exporting curve_scores_summary.json...")

    cs = pd.read_csv(processed_dir / 'curve_scores.csv').dropna(subset=['curve_score'])
    scored = pd.read_csv(processed_dir / 'name_changes_scored.csv')
    trans_names = set(scored[scored['gender_delta'].abs() >= 0.7]['new_first_name'])
    mean_delta = scored.groupby('new_first_name')['gender_delta'].mean()

    agg = cs.groupby('new_first_name')['curve_score'].agg(['mean', 'count']).reset_index()

    result = {}
    for _, row in agg.iterrows():
        name = row['new_first_name']
        delta = mean_delta.get(name, 0.0)
        if delta >= 0.7:
            direction = 'MTF'
        elif delta <= -0.7:
            direction = 'FTM'
        else:
            direction = 'unclear'
        result[name] = {
            'mean_cs': round(float(row['mean']), 4),
            'n': int(row['count']),
            'dir': direction,
            'gender': gender_map.get(name, 'N'),
            'is_trans': name in trans_names,
        }

    out_path.write_text(json.dumps(result))
    print(f"    -> {out_path} ({out_path.stat().st_size//1024} KB, {len(result):,} names)")


def main():
    parser = argparse.ArgumentParser(description='Export JSON data files for the web app')
    parser.add_argument('--raw-dir', default='data/raw')
    parser.add_argument('--processed-dir', default='data/processed')
    parser.add_argument('--output-dir', default='app/data')
    args = parser.parse_args()

    raw = Path(args.raw_dir)
    proc = Path(args.processed_dir)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    print("Loading baby name data...")
    baby = load_baby_names(
        raw / 'ontario_baby_names_female.csv',
        raw / 'ontario_baby_names_male.csv'
    )
    print(f"  {len(baby):,} rows loaded")

    print("\nExporting JSON files...")
    export_summary(proc, out / 'summary.json')
    export_baby_names(baby, out / 'baby_names.json')
    export_name_changes(proc, out / 'name_changes.json')
    export_correlation(proc, out / 'correlation.json')
    gender_map = compute_gender_map(baby)
    export_curve_summary(proc, out / 'curve_scores_summary.json', gender_map)

    # Copy research report into app for static serving
    report_src = Path('docs/REPORT.md')
    report_dst = out.parent / 'report.md'
    if report_src.exists():
        import shutil
        shutil.copy(report_src, report_dst)
        print(f"  Copied {report_src} -> {report_dst}")

    total = sum(f.stat().st_size for f in out.glob('*.json'))
    print(f"\nDone. Total: {total/1_000_000:.1f} MB in {out}/")


if __name__ == '__main__':
    main()

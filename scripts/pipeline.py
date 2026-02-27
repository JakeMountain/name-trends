#!/usr/bin/env python3
"""
pipeline.py

Orchestrates the full overnight workflow:
  1. Waits for gazette scrape to finish (polls gazette_pdfs/ count)
  2. Runs scripts/audit.py — diagnoses parser yield by year, flags anomalies
  3. Runs scripts/analyze.py — gender delta, lag analysis, MTF/FTM, dose-response
  4. Runs scripts/visualize.py — interactive Plotly HTML outputs

Usage:
    source .venv/Scripts/activate
    python scripts/pipeline.py > overnight.log 2>&1

Or to start immediately without waiting for scrape:
    python scripts/pipeline.py --skip-wait
"""

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


TARGET_PDF_COUNT = 1235
CACHE_DIR = Path('gazette_pdfs')
CSV_PATH = Path('data/raw/ontario_name_changes.csv')
CHECK_INTERVAL_SEC = 600   # poll every 10 minutes
STABLE_CHECKS_NEEDED = 2   # CSV row count must be stable for this many consecutive checks


def log(msg: str):
    print(f'[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}', flush=True)


def run(cmd: list[str], label: str) -> int:
    log(f'Starting: {label}')
    log(f'  cmd: {" ".join(cmd)}')
    result = subprocess.run(cmd)
    if result.returncode == 0:
        log(f'Done: {label}')
    else:
        log(f'WARNING: {label} exited with code {result.returncode}')
    return result.returncode


def pdf_count() -> int:
    return len(list(CACHE_DIR.glob('gazette_v*.pdf')))


def csv_row_count() -> int:
    if not CSV_PATH.exists():
        return 0
    with open(CSV_PATH, 'rb') as f:
        return sum(1 for _ in f)


def wait_for_scrape():
    log(f'Phase 1: Waiting for scrape to finish (target: {TARGET_PDF_COUNT} PDFs)...')
    stable_count = 0
    last_rows = -1

    while True:
        n_pdfs = pdf_count()
        n_rows = csv_row_count()
        log(f'  PDFs: {n_pdfs}/{TARGET_PDF_COUNT}   CSV rows: {n_rows:,}')

        if n_pdfs >= TARGET_PDF_COUNT:
            log('All PDFs cached — scrape complete.')
            return

        # Fallback: if row count has been stable for N checks, assume done
        if n_rows == last_rows and n_rows > 50_000:
            stable_count += 1
            log(f'  CSV stable for {stable_count}/{STABLE_CHECKS_NEEDED} checks.')
            if stable_count >= STABLE_CHECKS_NEEDED:
                log('CSV row count stable — assuming scrape complete.')
                return
        else:
            stable_count = 0

        last_rows = n_rows
        time.sleep(CHECK_INTERVAL_SEC)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--skip-wait', action='store_true',
                        help='Skip waiting for scrape; go straight to audit + analysis')
    parser.add_argument('--skip-audit', action='store_true')
    parser.add_argument('--skip-analysis', action='store_true')
    parser.add_argument('--skip-viz', action='store_true')
    args = parser.parse_args()

    python = sys.executable
    log('=== Overnight pipeline started ===')
    log(f'Python: {python}')

    # Phase 1: wait
    if not args.skip_wait:
        wait_for_scrape()
    else:
        log('Phase 1: Skipped (--skip-wait)')

    # Phase 2: audit
    if not args.skip_audit:
        log('\n=== Phase 2: Parser audit ===')
        rc = run([python, 'scripts/audit.py', '--cache-dir', 'gazette_pdfs', '--output-dir', 'audit'],
                 'scripts/audit.py')
        if rc != 0:
            log('Audit had errors — continuing anyway.')
        else:
            # Print flagged years summary
            flagged = Path('audit/flagged.txt')
            if flagged.exists():
                log('Flagged years found:')
                log(flagged.read_text())
            else:
                log('No flagged years — parser yield looks healthy across all years.')

    # Phase 3: analysis (multi-threshold, MTF/FTM, pre/post-2006)
    if not args.skip_analysis:
        log('\n=== Phase 3: Statistical analysis ===')
        run([
            python, 'scripts/analyze.py',
            '-n', 'data/raw/ontario_name_changes.csv',
            '-f', 'data/raw/ontario_baby_names_female.csv',
            '-m', 'data/raw/ontario_baby_names_male.csv',
            '-o', 'data/processed/',
            '--thresholds', '0.2,0.5,0.7',
        ], 'scripts/analyze.py')

    # Phase 4: interactive visualizations
    if not args.skip_viz:
        log('\n=== Phase 4: Visualizations ===')
        run([
            python, 'scripts/visualize.py',
            '-n', 'data/raw/ontario_name_changes.csv',
            '-f', 'data/raw/ontario_baby_names_female.csv',
            '-m', 'data/raw/ontario_baby_names_male.csv',
            '-r', 'data/processed/',
            '-o', 'viz/',
        ], 'scripts/visualize.py')

    log('\n=== Pipeline complete ===')
    log('Check:')
    log('  data/processed/     — CSVs + static PNGs')
    log('  viz/                — interactive HTML (open in browser)')
    log('  audit/by_year.csv   — parser yield by year')
    log('  audit/flagged.txt   — years needing spot-check (if any)')


if __name__ == '__main__':
    main()

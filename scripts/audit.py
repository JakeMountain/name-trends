#!/usr/bin/env python3
"""
audit_parser.py

Diagnoses gazette PDF parser yield: for each cached PDF, tries every regex
pattern independently, reports winner and record count, aggregates by year,
and flags anomalously-low-yield issues for manual review.

Usage:
    python audit_parser.py [--cache-dir gazette_pdfs] [--output-dir audit/]

Outputs:
    audit/detail.csv    — per-PDF results (volume, issue, year, winner, counts)
    audit/by_year.csv   — per-year aggregate with flagged anomalies
    audit/flagged.txt   — issues with suspiciously low yield (< 20 avg/issue)
"""

import argparse
import csv
import re
import sys
from collections import defaultdict
from pathlib import Path

try:
    import pdfplumber
except ImportError:
    print("pip install pdfplumber")
    sys.exit(1)

MAX_PAGES = 80  # stop reading after this many pages (name change section is always early)


# ── regex patterns (mirrors ontario_gazette_scraper.py) ──────────────────────

_MONTHS = r'(?:January|February|March|April|May|June|July|August|September|October|November|December)'
_U = 'A-ZÀ-ÖØ-Þ'            # uppercase ASCII + Latin-1 uppercase
_L = 'A-Za-zÀ-ÖØ-öø-ÿĀ-ž'  # all letters: ASCII + Latin-1 + Latin Extended-A

PATTERNS = {
    'modern_caps': re.compile(
        rf'(?:{_MONTHS}\s+\d{{1,2}},?\s+\d{{4}}\s+to\s+{_MONTHS}\s+\d{{1,2}},?\s+\d{{4}}\s+)?'
        rf'([{_U}][{_U}\-\']*(?:\s+[{_U}][{_U}\-\']*)*)'
        r',\s*'
        rf'([{_U}][{_U}\.\-\']+)'
        r'\.\s+'
        rf'([{_U}][{_U}\-\']*(?:\s+[{_U}][{_U}\-\']*)*)'
        r',\s*'
        rf'([{_U}][{_U}\.\-\']+)'
        r'\.',
        re.MULTILINE,
    ),
    'historical_to': re.compile(
        rf'([{_U}][{_U}\-\']+)\s*,\s*([{_L}][{_L}\-\'\s]+?)\s+to\s+'
        rf'([{_U}][{_U}\-\']+)\s*,\s*([{_L}][{_L}\-\'\s]+?)(?=\n|$|[{_U}]{{2,}}\s*,)',
        re.MULTILINE,
    ),
    'from_to': re.compile(
        rf'From:\s*([{_U}][{_L}\-\']+)\s*,\s*([{_L}][{_L}\-\'\s]+?)'
        rf'\s*To:\s*([{_U}][{_L}\-\']+)\s*,\s*([{_L}][{_L}\-\'\s]+)',
        re.IGNORECASE | re.DOTALL,
    ),
    'em_dash': re.compile(
        rf'([{_U}][{_L}\-\']+(?:\s+[{_U}][{_L}\-\']+)*)'
        r',\s*'
        rf'([{_L}][{_L}\.\-\'\s]+?)'
        r'\s*\u2014\s*'
        rf'([{_U}][{_L}\-\']+(?:\s+[{_U}][{_L}\-\']+)*)'
        r',\s*'
        rf'([{_L}][{_L}\.\-\'\s]+?)'
        r'(?=\s*\n|\s*\u2014|\s*$)',
        re.MULTILINE,
    ),
}

SECTION_START_RE = re.compile(r'NOTICES?\s+OF\s+CHANGE\s+OF\s+NAME|CHANGE\s+OF\s+NAME', re.IGNORECASE)
SECTION_END_RES = [
    re.compile(r'\n\s*NOTICE\s+OF\s+(?!CHANGE)', re.IGNORECASE),
    re.compile(r'\n\s*APPLICATIONS?\s+FOR', re.IGNORECASE),
    re.compile(r'\n\s*MINISTRY\s+OF', re.IGNORECASE),
    re.compile(r'\n\s*REGULATION', re.IGNORECASE),
]

FLAG_THRESHOLD = 20  # avg records/issue below this is suspicious


# ── helpers ───────────────────────────────────────────────────────────────────

def volume_to_year(volume: int) -> int:
    """Approximate year from gazette volume (Vol 133 ≈ 2000)."""
    return volume - 133 + 2000


def extract_section(text: str) -> str | None:
    m = SECTION_START_RE.search(text)
    if not m:
        return None
    start = m.start()
    end = len(text)
    for pat in SECTION_END_RES:
        m2 = pat.search(text, start + 1)
        if m2:
            end = min(end, m2.start())
    return text[start:end]


def count_valid_matches(pattern: re.Pattern, section: str) -> int:
    """Count matches where both first-name groups are >= 2 chars."""
    return sum(
        1 for m in pattern.findall(section)
        if len(m[1].strip()) >= 2 and len(m[3].strip()) >= 2
    )


# ── per-PDF audit ─────────────────────────────────────────────────────────────

def audit_pdf(pdf_path: Path) -> dict | None:
    """Stream pages, collect section text, stop as soon as section ends or MAX_PAGES hit."""
    m = re.match(r'gazette_v(\d+)_i(\d+)\.pdf', pdf_path.name)
    if not m:
        return None
    volume, issue = int(m.group(1)), int(m.group(2))
    year = volume_to_year(volume)

    row = {
        'volume': volume, 'issue': issue, 'year': year,
        'has_section': False, 'winner': '', 'winner_count': 0,
        'text_len': 0, 'error': '',
    }
    for pname in PATTERNS:
        row[f'count_{pname}'] = 0

    try:
        accumulated = ''
        section_started = False
        section_text = ''

        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages[:MAX_PAGES]):
                try:
                    page_text = page.extract_text() or ''
                except Exception:
                    continue

                accumulated += '\n' + page_text
                row['text_len'] += len(page_text)

                if not section_started:
                    sm = SECTION_START_RE.search(accumulated)
                    if sm:
                        section_started = True
                        section_text = accumulated[sm.start():]
                else:
                    section_text += '\n' + page_text
                    # Check if section has ended
                    for end_pat in SECTION_END_RES:
                        if end_pat.search(page_text):
                            # Trim at the end marker
                            em = end_pat.search(section_text)
                            if em:
                                section_text = section_text[:em.start()]
                            break
                    else:
                        continue
                    break  # section ended — no need to read more pages

    except Exception as e:
        row['error'] = str(e)
        return row

    if not section_started or not section_text.strip():
        return row

    row['has_section'] = True

    # Trim section at first end-marker found (in case we exited loop without trimming)
    for end_pat in SECTION_END_RES:
        em = end_pat.search(section_text, 1)
        if em:
            section_text = section_text[:em.start()]

    counts = {}
    for pname, pat in PATTERNS.items():
        n = count_valid_matches(pat, section_text)
        row[f'count_{pname}'] = n
        counts[pname] = n

    best = max(counts, key=counts.get)
    if counts[best] > 0:
        row['winner'] = best
        row['winner_count'] = counts[best]

    return row


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Audit gazette PDF parser yield by year/pattern')
    parser.add_argument('--cache-dir', default='gazette_pdfs')
    parser.add_argument('--output-dir', default='audit')
    args = parser.parse_args()

    cache_dir = Path(args.cache_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(exist_ok=True)

    pdfs = sorted(cache_dir.glob('gazette_v*.pdf'),
                  key=lambda p: (int(re.search(r'_v(\d+)', p.name).group(1)),
                                 int(re.search(r'_i(\d+)', p.name).group(1))))
    print(f'Found {len(pdfs)} cached PDFs in {cache_dir}/')

    detail_rows = []
    for i, pdf_path in enumerate(pdfs):
        row = audit_pdf(pdf_path)
        if row is None:
            continue
        detail_rows.append(row)
        if (i + 1) % 50 == 0 or i == 0:
            print(f'  [{i+1}/{len(pdfs)}] v{row["volume"]}i{row["issue"]} '
                  f'({row["year"]}): winner={row["winner"] or "none"} n={row["winner_count"]}',
                  flush=True)

    # Write detail CSV
    detail_path = output_dir / 'detail.csv'
    detail_fields = ['volume', 'issue', 'year', 'has_section', 'winner', 'winner_count',
                     'text_len', 'count_modern_caps', 'count_historical_to',
                     'count_from_to', 'count_em_dash', 'error']
    with open(detail_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=detail_fields, extrasaction='ignore')
        w.writeheader()
        w.writerows(detail_rows)
    print(f'\nDetail written to {detail_path}')

    # Aggregate by year
    by_year: dict[int, dict] = defaultdict(lambda: {
        'pdfs': 0, 'total_records': 0, 'with_section': 0,
        'pattern_wins': defaultdict(int),
    })
    for row in detail_rows:
        y = row['year']
        by_year[y]['pdfs'] += 1
        by_year[y]['total_records'] += row['winner_count']
        by_year[y]['with_section'] += int(bool(row['has_section']))
        if row['winner']:
            by_year[y]['pattern_wins'][row['winner']] += 1

    summary_rows = []
    for year in sorted(by_year):
        d = by_year[year]
        n = d['pdfs']
        avg = d['total_records'] / n if n > 0 else 0.0
        top_pat = (max(d['pattern_wins'], key=d['pattern_wins'].get)
                   if d['pattern_wins'] else 'none')
        flagged = avg < FLAG_THRESHOLD and d['with_section'] > 0
        summary_rows.append({
            'year': year,
            'pdfs': n,
            'total_records': d['total_records'],
            'avg_per_pdf': round(avg, 1),
            'pdfs_with_section': d['with_section'],
            'top_pattern': top_pat,
            'flagged': flagged,
        })

    summary_path = output_dir / 'by_year.csv'
    with open(summary_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=['year', 'pdfs', 'total_records', 'avg_per_pdf',
                                          'pdfs_with_section', 'top_pattern', 'flagged'])
        w.writeheader()
        w.writerows(summary_rows)

    # Print summary table
    print()
    print('=' * 72)
    print(f"{'year':>4}  {'pdfs':>4}  {'records':>8}  {'avg/pdf':>7}  "
          f"{'pattern':<16}  note")
    print('-' * 72)
    flagged_years = []
    for row in summary_rows:
        flag = '*** LOW YIELD' if row['flagged'] else ''
        print(f"{row['year']:>4}  {row['pdfs']:>4}  {row['total_records']:>8}  "
              f"{row['avg_per_pdf']:>7.1f}  {row['top_pattern']:<16}  {flag}")
        if row['flagged']:
            flagged_years.append(row['year'])
    print('=' * 72)
    print(f'\nSummary written to {summary_path}')

    if flagged_years:
        flagged_path = output_dir / 'flagged.txt'
        with open(flagged_path, 'w', encoding='utf-8') as f:
            f.write(f'Years with avg < {FLAG_THRESHOLD} records/issue (but section present):\n')
            for y in flagged_years:
                yr_rows = [r for r in detail_rows if r['year'] == y and r['has_section'] and r['winner_count'] == 0]
                sample = yr_rows[:3]
                f.write(f'\n  {y} — sample zero-yield PDFs:\n')
                for r in sample:
                    fname = f'gazette_pdfs/gazette_v{r["volume"]}_i{r["issue"]}.pdf'
                    f.write(f'    {fname}\n')
            f.write('\nTo inspect a flagged PDF:\n')
            f.write('  python -c "import pdfplumber; pdf=pdfplumber.open(\'PATH\'); '
                    'print(pdf.pages[0].extract_text()[:3000])"\n')
        print(f'Flagged years ({flagged_years}) written to {flagged_path}')
    else:
        print('No flagged years — yield looks consistent across all years.')


if __name__ == '__main__':
    main()

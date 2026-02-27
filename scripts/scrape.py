#!/usr/bin/env python3
"""
Ontario Gazette Name Change Scraper

Scrapes legal name changes from the Ontario Gazette (2000-present).
Outputs CSV with: old_first_name, old_last_name, new_first_name, new_last_name, gazette_date

Usage:
    python scripts/scrape.py --start-year 2000 --end-year 2024 --output data/raw/ontario_name_changes.csv

Requirements:
    pip install requests beautifulsoup4 pdfplumber tqdm
"""

import argparse
import csv
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
import logging

try:
    import requests
    from bs4 import BeautifulSoup
    import pdfplumber
    from tqdm import tqdm
except ImportError as e:
    print(f"Missing dependency: {e}")
    print("Install with: pip install requests beautifulsoup4 pdfplumber tqdm")
    exit(1)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BASE_URL = "https://www.ontario.ca"
SEARCH_URL = "https://www.ontario.ca/search/ontario-gazette"
RATE_LIMIT = 1.0


class GazetteScraper:
    def __init__(self, cache_dir: Path):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(exist_ok=True)
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0 (research project)'})
    
    def get_gazette_index(self, start_year: int, end_year: int) -> list[dict]:
        """Fetch list of all Gazette issues."""
        gazettes = []
        page = 0
        
        logger.info(f"Fetching Gazette index for {start_year}-{end_year}...")
        
        while True:
            try:
                resp = self.session.get(SEARCH_URL, params={'page': page}, timeout=30)
                resp.raise_for_status()
            except requests.RequestException as e:
                logger.error(f"Failed page {page}: {e}")
                break
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            found = False
            
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                text = link.get_text(strip=True)
                
                if '/document/ontario-gazette-volume-' in href:
                    found = True
                    match = re.search(
                        r'Volume\s+(\d+)\s+Issue\s+(\d+)\s*\|\s*(\w+\s+\d+,?\s+\d{4})',
                        text, re.IGNORECASE
                    )
                    if match:
                        volume, issue = int(match.group(1)), int(match.group(2))
                        date_str = match.group(3).replace(',', '')
                        try:
                            gazette_date = datetime.strptime(date_str, '%B %d %Y')
                            if start_year <= gazette_date.year <= end_year:
                                gazettes.append({
                                    'title': text,
                                    'url': BASE_URL + href if href.startswith('/') else href,
                                    'date': gazette_date,
                                    'volume': volume,
                                    'issue': issue
                                })
                        except ValueError:
                            pass
            
            if not found:
                break
            
            # Stop if we've gone past our date range
            if gazettes and gazettes[-1]['date'].year < start_year:
                break
            
            page += 1
            time.sleep(RATE_LIMIT)
            if page > 200:
                break
        
        gazettes.sort(key=lambda x: x['date'])
        logger.info(f"Found {len(gazettes)} gazette issues")
        return gazettes
    
    def get_pdf_url(self, page_url: str) -> Optional[str]:
        """Find PDF download link on gazette page."""
        try:
            resp = self.session.get(page_url, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Failed to fetch {page_url}: {e}")
            return None
        
        soup = BeautifulSoup(resp.text, 'html.parser')
        for link in soup.find_all('a', href=True):
            href = link.get('href', '')
            text = link.get_text(strip=True).lower()
            if '.pdf' in href.lower() or 'pdf' in text:
                return BASE_URL + href if href.startswith('/') else href
        return None
    
    def download_pdf(self, pdf_url: str, gazette: dict) -> Optional[Path]:
        """Download PDF with caching."""
        cache_file = self.cache_dir / f"gazette_v{gazette['volume']}_i{gazette['issue']}.pdf"
        
        if cache_file.exists():
            return cache_file
        
        try:
            resp = self.session.get(pdf_url, timeout=60)
            resp.raise_for_status()
            cache_file.write_bytes(resp.content)
            return cache_file
        except requests.RequestException as e:
            logger.error(f"Failed to download {pdf_url}: {e}")
            return None
    
    def extract_name_changes(self, pdf_path: Path, gazette: dict) -> list[dict]:
        """Extract name changes from PDF."""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                text = "\n".join(p.extract_text() or "" for p in pdf.pages)
        except Exception as e:
            logger.error(f"Failed to read {pdf_path}: {e}")
            return []
        
        # Find name change section
        section_start = None
        for pattern in [r'NOTICES?\s+OF\s+CHANGE\s+OF\s+NAME', r'CHANGE\s+OF\s+NAME']:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                section_start = match.start()
                break
        
        if section_start is None:
            return []
        
        # Find section end
        section_end = len(text)
        for pattern in [r'\n\s*NOTICE\s+OF\s+(?!CHANGE)', r'\n\s*APPLICATIONS?\s+FOR',
                        r'\n\s*MINISTRY\s+OF', r'\n\s*REGULATION']:
            match = re.search(pattern, text[section_start:], re.IGNORECASE)
            if match:
                section_end = min(section_end, section_start + match.start())
        
        section = text[section_start:section_end]
        
        # Parse name changes
        _MONTHS = r'(?:January|February|March|April|May|June|July|August|September|October|November|December)'
        # Unicode letter ranges: uppercase includes Latin-1 uppercase block (ÀÁÂÃÄÅÆÇ…ÐÑ…ÖØ…Þ)
        # mixed case includes Latin-1 + Latin Extended-A (Āā–Žž) for Franco-phone / immigrant names.
        _U = 'A-ZÀ-ÖØ-Þ'            # uppercase ASCII + Latin-1 uppercase
        _L = 'A-Za-zÀ-ÖØ-öø-ÿĀ-ž'  # all letters: ASCII + Latin-1 + Latin Extended-A
        patterns = [
            # Modern gazette format (2000s+, verified against actual PDFs):
            # "December 18, 2023 to December 24, 2023 ABDULAHAD, MELISSIA. BUTRUS, MELISSIA."
            # Names in ALL CAPS; dots join first/middle name parts; period+space separates old from new.
            re.compile(
                rf'(?:{_MONTHS}\s+\d{{1,2}},?\s+\d{{4}}\s+to\s+{_MONTHS}\s+\d{{1,2}},?\s+\d{{4}}\s+)?'
                rf'([{_U}][{_U}\-\']*(?:\s+[{_U}][{_U}\-\']*)*)'  # old last name (compound ok)
                r',\s*'
                rf'([{_U}][{_U}\.\-\']+)'  # old first+middle (dots as separators, e.g. ELLA.FAAIZ)
                r'\.\s+'  # end of old name: period then space
                rf'([{_U}][{_U}\-\']*(?:\s+[{_U}][{_U}\-\']*)*)'  # new last name
                r',\s*'
                rf'([{_U}][{_U}\.\-\']+)'  # new first+middle
                r'\.',
                re.MULTILINE
            ),
            # Historical format: LAST, First to LAST, First
            re.compile(
                rf'([{_U}][{_U}\-\']+)\s*,\s*([{_L}][{_L}\-\'\s]+?)\s+to\s+'
                rf'([{_U}][{_U}\-\']+)\s*,\s*([{_L}][{_L}\-\'\s]+?)(?=\n|$|[{_U}]{{2,}}\s*,)',
                re.MULTILINE,
            ),
            # From: LAST, First To: LAST, First
            re.compile(
                rf'From:\s*([{_U}][{_L}\-\']+)\s*,\s*([{_L}][{_L}\-\'\s]+?)'
                rf'\s*To:\s*([{_U}][{_L}\-\']+)\s*,\s*([{_L}][{_L}\-\'\s]+)',
                re.IGNORECASE | re.DOTALL,
            ),
            # Early gazette format (~2000-2009): Title Case, em-dash separator
            # "Clark, Pamela Jean \u2014 Lawlor, Pamela Jean"
            re.compile(
                rf'([{_U}][{_L}\-\']+(?:\s+[{_U}][{_L}\-\']+)*)'  # old last name
                r',\s*'
                rf'([{_L}][{_L}\.\-\'\s]+?)'  # old first+middle (title case)
                r'\s*\u2014\s*'  # em-dash separator
                rf'([{_U}][{_L}\-\']+(?:\s+[{_U}][{_L}\-\']+)*)'  # new last name
                r',\s*'
                rf'([{_L}][{_L}\.\-\'\s]+?)'  # new first+middle
                r'(?=\s*\n|\s*\u2014|\s*$)',
                re.MULTILINE,
            ),
        ]

        changes = []
        for pattern in patterns:
            for match in pattern.findall(section):
                old_last, old_first, new_last, new_first = [' '.join(s.split()) for s in match]

                if len(old_first) < 2 or len(new_first) < 2:
                    continue

                changes.append({
                    'old_first_name': re.split(r'[.\s]', old_first)[0],
                    'old_full_first': old_first,
                    'old_last_name': old_last,
                    'new_first_name': re.split(r'[.\s]', new_first)[0],
                    'new_full_first': new_first,
                    'new_last_name': new_last,
                    'gazette_date': gazette['date'].strftime('%Y-%m-%d'),
                    'gazette_volume': gazette['volume'],
                    'gazette_issue': gazette['issue'],
                })

            if changes:
                break
        
        logger.info(f"Extracted {len(changes)} from {pdf_path.name}")
        return changes
    
    def scrape(self, start_year: int, end_year: int, output_file: str,
               limit: Optional[int] = None, skip_download: bool = False):
        """Main scraping function. Writes incrementally; safe to interrupt and resume."""
        gazettes = self.get_gazette_index(start_year, end_year)
        if limit:
            gazettes = gazettes[:limit]

        fields = ['old_first_name', 'old_full_first', 'old_last_name',
                  'new_first_name', 'new_full_first', 'new_last_name',
                  'gazette_date', 'gazette_volume', 'gazette_issue']

        # Load already-processed issues so we can skip them on resume.
        done_keys: set[tuple[int, int]] = set()
        output_path = Path(output_file)
        if output_path.exists():
            with open(output_file, 'r', encoding='utf-8') as f:
                for row in csv.DictReader(f):
                    done_keys.add((int(row['gazette_volume']), int(row['gazette_issue'])))
            logger.info(f"Resuming: {len(done_keys)} issues already in {output_file}")

        write_mode = 'a' if output_path.exists() else 'w'
        total_records = 0

        with open(output_file, write_mode, newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=fields)
            if write_mode == 'w':
                writer.writeheader()

            for gazette in tqdm(gazettes, desc="Processing"):
                key = (gazette['volume'], gazette['issue'])
                if key in done_keys:
                    continue

                # If the PDF is already cached we can skip the HTTP lookup entirely.
                pdf_path = self.cache_dir / f"gazette_v{gazette['volume']}_i{gazette['issue']}.pdf"
                if not pdf_path.exists():
                    if skip_download:
                        continue
                    time.sleep(RATE_LIMIT)
                    pdf_url = self.get_pdf_url(gazette['url'])
                    if not pdf_url:
                        continue
                    time.sleep(RATE_LIMIT)
                    pdf_path = self.download_pdf(pdf_url, gazette)
                    if not pdf_path:
                        continue

                changes = self.extract_name_changes(pdf_path, gazette)
                if changes:
                    writer.writerows(changes)
                    f.flush()
                    total_records += len(changes)

        logger.info(f"Done. Wrote {total_records} new records to {output_file}")
        return []


def main():
    parser = argparse.ArgumentParser(description='Scrape Ontario Gazette name changes')
    parser.add_argument('--start-year', type=int, default=2000)
    parser.add_argument('--end-year', type=int, default=2024)
    parser.add_argument('--output', '-o', default='data/raw/ontario_name_changes.csv')
    parser.add_argument('--cache-dir', default='gazette_pdfs')
    parser.add_argument('--limit', type=int, help='Limit issues (for testing)')
    parser.add_argument('--skip-download', action='store_true')
    parser.add_argument('--verbose', '-v', action='store_true')
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    scraper = GazetteScraper(Path(args.cache_dir))
    scraper.scrape(args.start_year, args.end_year, args.output, 
                   limit=args.limit, skip_download=args.skip_download)


if __name__ == '__main__':
    main()
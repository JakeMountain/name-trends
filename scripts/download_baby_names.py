#!/usr/bin/env python3
"""Download Ontario Baby Names data."""

import requests

URLS = {
    'female': "https://data.ontario.ca/dataset/4d339626-98f9-49fe-aede-d64f03fa914f/resource/5d2df591-33d4-4b36-bb1d-e3d8d74633ae/download/ontario_top_baby_names_female.csv",
    'male': "https://data.ontario.ca/dataset/eb4c585c-6ada-4de7-8ff1-e876fb1a6b0b/resource/9571139d-e505-4a35-82fa-192af66c5714/download/ontario_top_baby_names_male.csv"
}

def main():
    for label, url in URLS.items():
        outfile = f"ontario_baby_names_{label}.csv"
        print(f"Downloading {outfile}...")
        resp = requests.get(url)
        resp.raise_for_status()
        with open(outfile, 'wb') as f:
            f.write(resp.content)
        print(f"  Saved ({len(resp.content):,} bytes)")
    
    print("\nDone! Files:")
    print("  ontario_baby_names_female.csv (1913-2023)")
    print("  ontario_baby_names_male.csv (1917-2023)")

if __name__ == '__main__':
    main()
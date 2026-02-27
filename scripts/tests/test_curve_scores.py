#!/usr/bin/env python3
"""
Tests and spot-checks for the curve score implementation.

Run with:
    source .venv/Scripts/activate
    python scripts/tests/test_curve_scores.py
"""
import sys
from pathlib import Path
import pandas as pd
import numpy as np

# Import the functions we're testing
sys.path.insert(0, str(Path(__file__).parent.parent))
from analyze import build_baby_rel_freq, compute_curve_scores, load_baby_names


# =============================================================================
# UNIT TESTS WITH CONSTRUCTED DATA
# =============================================================================

def make_toy_baby(rows):
    """Build a minimal baby DataFrame from (name, year, count) tuples."""
    df = pd.DataFrame(rows, columns=['first_name', 'year', 'count'])
    return df


def make_toy_nc(rows):
    """Build a minimal name-change DataFrame."""
    df = pd.DataFrame(rows, columns=['old_first_name', 'new_first_name',
                                     'gazette_date', 'year', 'gender_delta'])
    return df


def test_rising_name_scores_positive():
    """
    ALICE becomes popular AFTER 2009.
    Expected: curve_score > 0 (ahead of curve).
    """
    # 100 babies/year uniformly distributed across all years (for denominator)
    years = list(range(2000, 2024))
    base_rows = [('OTHER', y, 1000) for y in years]  # denominator filler
    # ALICE: 10 before 2009 (split over 5 years), 50 after (split over 5 years)
    alice_rows = [(f'ALICE', y, 2) for y in range(2004, 2009)]   # before: 5y * 2 = 10
    alice_rows += [(f'ALICE', y, 10) for y in range(2010, 2015)] # after:  5y * 10 = 50

    baby_df = make_toy_baby(base_rows + alice_rows)
    # Split into "female" df (all ALICE) and "male" (no overlap)
    baby_f = baby_df[baby_df['first_name'] == 'ALICE'].copy()
    baby_m = baby_df[baby_df['first_name'] == 'OTHER'].copy()

    nc = make_toy_nc([('BOB', 'ALICE', '2009-06-01', 2009, 1.0)])
    nc_scored = nc.copy()
    nc_scored['gender_delta'] = 1.0

    import tempfile, os
    with tempfile.TemporaryDirectory() as tmpdir:
        result = compute_curve_scores(nc_scored, baby_f, baby_m,
                                      Path(tmpdir), window=5,
                                      year_min=2009, year_max=2009)

    score = result['curve_score'].iloc[0]
    assert score > 0, f"Expected positive score for rising name ALICE, got {score:.4f}"
    # before_freq = 5 * (2/1002) ≈ 0.00998
    # after_freq  = 5 * (10/1010) ≈ 0.04950
    # score = (0.0495 - 0.00998) / (0.0495 + 0.00998) ≈ +0.66
    print(f"  PASS  test_rising_name_scores_positive: score={score:.4f} (expected >0)")


def test_declining_name_scores_negative():
    """
    KAREN was popular BEFORE 2009 and has faded since.
    Expected: curve_score < 0 (behind the curve).
    """
    years = list(range(2000, 2024))
    base_rows = [('OTHER', y, 1000) for y in years]
    karen_rows = [('KAREN', y, 10) for y in range(2004, 2009)]  # before: heavy
    karen_rows += [('KAREN', y, 2)  for y in range(2010, 2015)] # after: light

    baby_df = make_toy_baby(base_rows + karen_rows)
    baby_f = baby_df[baby_df['first_name'] == 'KAREN'].copy()
    baby_m = baby_df[baby_df['first_name'] == 'OTHER'].copy()

    nc = make_toy_nc([('KYLE', 'KAREN', '2009-06-01', 2009, 1.0)])
    nc_scored = nc.copy()

    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        result = compute_curve_scores(nc_scored, baby_f, baby_m,
                                      Path(tmpdir), window=5,
                                      year_min=2009, year_max=2009)

    score = result['curve_score'].iloc[0]
    assert score < 0, f"Expected negative score for declining name KAREN, got {score:.4f}"
    print(f"  PASS  test_declining_name_scores_negative: score={score:.4f} (expected <0)")


def test_unknown_name_scores_nan():
    """
    ZXQWERTY does not exist in baby data.
    Expected: curve_score is NaN.
    """
    baby_f = make_toy_baby([('ALICE', 2005, 10), ('ALICE', 2010, 20)])
    baby_m = make_toy_baby([('BOB', 2005, 10)])

    nc = make_toy_nc([('OLD', 'ZXQWERTY', '2009-01-01', 2009, 0.9)])

    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        result = compute_curve_scores(nc, baby_f, baby_m,
                                      Path(tmpdir), window=5,
                                      year_min=2009, year_max=2009)

    score = result['curve_score'].iloc[0]
    assert pd.isna(score), f"Expected NaN for unknown name, got {score}"
    print(f"  PASS  test_unknown_name_scores_nan: score={score} (expected NaN)")


def test_only_before_window_scores_minus_one():
    """
    Name only appears in baby data BEFORE the change year.
    Expected: curve_score = -1.0 exactly.
    """
    base = [('OTHER', y, 1000) for y in range(2000, 2024)]
    name_rows = [('OLDNAME', y, 5) for y in range(2004, 2009)]  # only before 2009

    baby_f = make_toy_baby(base + name_rows)
    baby_m = make_toy_baby([('OTHER2', 2005, 1)])

    nc = make_toy_nc([('X', 'OLDNAME', '2009-01-01', 2009, 1.0)])

    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        result = compute_curve_scores(nc, baby_f, baby_m,
                                      Path(tmpdir), window=5,
                                      year_min=2009, year_max=2009)

    score = result['curve_score'].iloc[0]
    assert score == -1.0, f"Expected -1.0 for name only in before window, got {score:.4f}"
    print(f"  PASS  test_only_before_window_scores_minus_one: score={score:.4f}")


def test_only_after_window_scores_plus_one():
    """
    Name only appears in baby data AFTER the change year.
    Expected: curve_score = +1.0 exactly.
    """
    base = [('OTHER', y, 1000) for y in range(2000, 2024)]
    name_rows = [('NEWNAME', y, 5) for y in range(2010, 2015)]  # only after 2009

    baby_f = make_toy_baby(base + name_rows)
    baby_m = make_toy_baby([('OTHER2', 2005, 1)])

    nc = make_toy_nc([('X', 'NEWNAME', '2009-01-01', 2009, 1.0)])

    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        result = compute_curve_scores(nc, baby_f, baby_m,
                                      Path(tmpdir), window=5,
                                      year_min=2009, year_max=2009)

    score = result['curve_score'].iloc[0]
    assert score == 1.0, f"Expected +1.0 for name only in after window, got {score:.4f}"
    print(f"  PASS  test_only_after_window_scores_plus_one: score={score:.4f}")


def test_arithmetic_spot_check():
    """
    Manual arithmetic check with known values.
    NAME appears:
      2004: 10 of 1010 total  → rel_freq = 10/1010
      2005: 20 of 1020 total  → rel_freq = 20/1020
      ...
    Year of change = 2009.
    before = sum rel_freq for 2004-2008
    after  = sum rel_freq for 2010-2014
    """
    rows = []
    for y in range(2000, 2024):
        rows.append(('OTHER', y, 1000))
        rows.append(('NAME', y, y - 2000))  # count = 0,1,2,...23

    baby_f = make_toy_baby(rows)
    baby_m = make_toy_baby([('PAD', 1999, 1)])  # outside 2004-2014 window

    # baby_m has a single PAD row in year 1999 (outside the window) so it
    # does not affect the 2004-2014 year totals used in the manual calculation.
    baby_m = make_toy_baby([('PAD', 1999, 1)])

    nc = make_toy_nc([('X', 'NAME', '2009-01-01', 2009, 1.0)])

    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        result = compute_curve_scores(nc, baby_f, baby_m,
                                      Path(tmpdir), window=5,
                                      year_min=2009, year_max=2009)

    # Manual calculation: total per year = OTHER(1000) + NAME(y-2000); PAD is in 1999 only
    expected_before = sum((y - 2000) / (1000 + (y - 2000)) for y in range(2004, 2009))
    expected_after  = sum((y - 2000) / (1000 + (y - 2000)) for y in range(2010, 2015))
    total = expected_before + expected_after
    expected_score = (expected_after - expected_before) / total

    actual_score = result['curve_score'].iloc[0]
    diff = abs(actual_score - expected_score)
    assert diff < 1e-6, f"Arithmetic mismatch: expected {expected_score:.6f}, got {actual_score:.6f}"
    print(f"  PASS  test_arithmetic_spot_check: score={actual_score:.6f} (expected {expected_score:.6f})")


# =============================================================================
# REAL-DATA SPOT-CHECKS
# =============================================================================

def real_data_spot_checks():
    """
    Load real data and spot-check scores for JENNIFER (should be negative)
    and OLIVER (should be positive), printing raw numbers for human verification.
    """
    print("\n" + "="*60)
    print("REAL-DATA SPOT-CHECKS")
    print("="*60)

    _root = Path(__file__).parent.parent.parent
    baby_f = load_baby_names(str(_root / 'data/raw/ontario_baby_names_female.csv'))
    baby_m = load_baby_names(str(_root / 'data/raw/ontario_baby_names_male.csv'))

    from analyze import build_baby_rel_freq
    lookup = build_baby_rel_freq(baby_f, baby_m)

    # Helper: print window for a given name and year
    def show_window(name, year, window=5):
        print(f"\n  {name} around {year} (window={window}y):")
        rows = lookup[lookup['first_name'] == name].set_index('year')['rel_freq']
        before_sum = 0.0
        after_sum  = 0.0
        for y in range(year - window, year + window + 1):
            if y == year:
                print(f"    {y}  [CHANGE YEAR — excluded]")
                continue
            rf = rows.get(y, 0.0)
            tag = "before" if y < year else "after "
            print(f"    {y}  {tag}  rel_freq={rf:.6f}")
            if y < year:
                before_sum += rf
            else:
                after_sum += rf
        total = before_sum + after_sum
        score = (after_sum - before_sum) / total if total > 0 else float('nan')
        print(f"    before_sum={before_sum:.6f}  after_sum={after_sum:.6f}  "
              f"score={score:+.4f}")
        return score

    # JENNIFER: peaked ~1975, should be strongly negative by 2009-2015
    jennifer_score = show_window('JENNIFER', 2009)
    assert jennifer_score < 0, f"JENNIFER should be negative, got {jennifer_score:.4f}"
    print(f"  CHECK: JENNIFER score {jennifer_score:+.4f} < 0  PASS")

    # OLIVER: surging through 2013-2018, should be positive
    oliver_score = show_window('OLIVER', 2013)
    assert oliver_score > 0, f"OLIVER should be positive, got {oliver_score:.4f}"
    print(f"  CHECK: OLIVER score {oliver_score:+.4f} > 0  PASS")

    # KAI: very recent trend name, should be strongly positive for 2013-2018 changes
    kai_score = show_window('KAI', 2015)
    print(f"  KAI score at 2015: {kai_score:+.4f}  (expected positive)")

    # JESSICA: peaked ~1991, should be strongly negative throughout our window
    jessica_score = show_window('JESSICA', 2009)
    assert jessica_score < 0, f"JESSICA should be negative, got {jessica_score:.4f}"
    print(f"  CHECK: JESSICA score {jessica_score:+.4f} < 0  PASS")


# =============================================================================
# MAIN
# =============================================================================

if __name__ == '__main__':
    print("=" * 60)
    print("UNIT TESTS (constructed data)")
    print("=" * 60)

    tests = [
        test_rising_name_scores_positive,
        test_declining_name_scores_negative,
        test_unknown_name_scores_nan,
        test_only_before_window_scores_minus_one,
        test_only_after_window_scores_plus_one,
        test_arithmetic_spot_check,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  FAIL  {test.__name__}: {e}")
            failed += 1

    print(f"\n{passed}/{passed+failed} unit tests passed")

    # Real data spot-checks (require data/raw/ontario_baby_names_*.csv)
    try:
        real_data_spot_checks()
        print("\nAll spot-checks passed.")
    except FileNotFoundError as e:
        print(f"\nSkipping real-data spot-checks (file not found): {e}")
    except Exception as e:
        print(f"\nSpot-check FAILED: {e}")
        raise

    if failed > 0:
        sys.exit(1)
    print("\nAll tests passed.")

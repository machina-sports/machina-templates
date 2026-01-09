"""
Tests for season type detection logic.
"""

import sys
from pathlib import Path

# Add parent directory to path
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

from detect_season_type import detect_season_type


def test_preseason():
    """Test preseason detection (weeks 0-4)."""
    request_data = {
        "params": {
            "week_sequence": 2,
            "api_season_type": "PRE"
        }
    }

    result = detect_season_type(request_data)

    assert result['status'] == True
    assert result['data']['season_type'] == 'PRE'
    assert result['data']['corrected'] == False
    print("✓ Preseason test passed")


def test_regular_season():
    """Test regular season detection (weeks 1-18)."""
    request_data = {
        "params": {
            "week_sequence": 10,
            "api_season_type": "REG"
        }
    }

    result = detect_season_type(request_data)

    assert result['status'] == True
    assert result['data']['season_type'] == 'REG'
    assert result['data']['corrected'] == False
    print("✓ Regular season test passed")


def test_playoffs_correction():
    """Test playoff detection with correction (week >= 19)."""
    request_data = {
        "params": {
            "week_sequence": 19,
            "api_season_type": "REG"  # API returns wrong value
        }
    }

    result = detect_season_type(request_data)

    assert result['status'] == True
    assert result['data']['season_type'] == 'PST'
    assert result['data']['corrected'] == True
    assert result['data']['api_season_type'] == 'REG'
    assert result['data']['pst_week'] == 1  # Week 19 → PST week 1
    print("✓ Playoffs correction test passed (week 19 → PST week 1)")


def test_current_scenario():
    """Test current scenario: week 18 after Jan 6 should be PST."""
    request_data = {
        "params": {
            "week_sequence": 18,
            "api_season_type": "REG"
        }
    }

    result = detect_season_type(request_data)

    # Week 18 after Jan 6 should be detected as PST
    from datetime import datetime
    current_date = datetime.now()

    if current_date.month == 1 and current_date.day >= 6:
        assert result['status'] == True
        assert result['data']['season_type'] == 'PST'
        assert result['data']['corrected'] == True
        assert 'Jan 6' in result['data']['reason']
        print("✓ Week 18 after Jan 6 (PST) test passed")
    else:
        # Before playoffs, week 18 should be REG
        assert result['status'] == True
        assert result['data']['season_type'] == 'REG'
        assert result['data']['corrected'] == False
        print("✓ Week 18 before playoffs (REG) test passed")


def test_wild_card_round():
    """Test Wild Card round (week 19)."""
    request_data = {
        "params": {
            "week_sequence": 19,
            "api_season_type": "REG"
        }
    }

    result = detect_season_type(request_data)

    assert result['status'] == True
    assert result['data']['season_type'] == 'PST'
    assert result['data']['corrected'] == True
    assert result['data']['pst_week'] == 1  # Wild Card = PST week 1
    print("✓ Wild Card round test passed (week 19 → PST week 1)")


def test_missing_week():
    """Test missing week_sequence parameter."""
    request_data = {
        "params": {
            "api_season_type": "REG"
        }
    }

    result = detect_season_type(request_data)

    assert result['status'] == False
    assert 'required' in result['message']
    print("✓ Missing week test passed")


def test_season_year_january():
    """Test season_year calculation for January (previous year)."""
    from datetime import datetime

    # Any request in January should return previous year
    request_data = {
        "params": {
            "week_sequence": 19,
            "api_season_type": "PST"
        }
    }

    result = detect_season_type(request_data)

    assert result['status'] == True
    assert 'season_year' in result['data']

    # If running in January, should be previous year
    current_date = datetime.now()
    if current_date.month == 1:
        expected_year = current_date.year - 1
        assert result['data']['season_year'] == expected_year
        print(f"✓ Season year January test passed (Jan {current_date.year} → {expected_year} season)")
    else:
        print("✓ Season year January test skipped (not January)")


def test_season_year_july():
    """Test season_year calculation for July (previous year)."""
    from datetime import datetime

    request_data = {
        "params": {
            "week_sequence": 1,
            "api_season_type": "PRE"
        }
    }

    result = detect_season_type(request_data)

    assert result['status'] == True
    assert 'season_year' in result['data']

    # If running in July, should be previous year
    current_date = datetime.now()
    if current_date.month == 7:
        expected_year = current_date.year - 1
        assert result['data']['season_year'] == expected_year
        print(f"✓ Season year July test passed (Jul {current_date.year} → {expected_year} season)")
    else:
        print("✓ Season year July test skipped (not July)")


def test_season_year_august():
    """Test season_year calculation for August (current year)."""
    from datetime import datetime

    request_data = {
        "params": {
            "week_sequence": 1,
            "api_season_type": "PRE"
        }
    }

    result = detect_season_type(request_data)

    assert result['status'] == True
    assert 'season_year' in result['data']

    # If running in August, should be current year
    current_date = datetime.now()
    if current_date.month == 8:
        expected_year = current_date.year
        assert result['data']['season_year'] == expected_year
        print(f"✓ Season year August test passed (Aug {current_date.year} → {expected_year} season)")
    else:
        print("✓ Season year August test skipped (not August)")


def test_season_year_december():
    """Test season_year calculation for December (current year)."""
    from datetime import datetime

    request_data = {
        "params": {
            "week_sequence": 17,
            "api_season_type": "REG"
        }
    }

    result = detect_season_type(request_data)

    assert result['status'] == True
    assert 'season_year' in result['data']

    # If running in December, should be current year
    current_date = datetime.now()
    if current_date.month == 12:
        expected_year = current_date.year
        assert result['data']['season_year'] == expected_year
        print(f"✓ Season year December test passed (Dec {current_date.year} → {expected_year} season)")
    else:
        print("✓ Season year December test skipped (not December)")


def test_season_year_always_present():
    """Test that season_year is always returned."""
    request_data = {
        "params": {
            "week_sequence": 10,
            "api_season_type": "REG"
        }
    }

    result = detect_season_type(request_data)

    assert result['status'] == True
    assert 'season_year' in result['data']
    assert isinstance(result['data']['season_year'], int)
    assert result['data']['season_year'] > 2020  # Sanity check
    print(f"✓ Season year always present test passed (year: {result['data']['season_year']})")


def test_pst_week_conversion():
    """Test PST week conversion (19→1, 20→2, etc.)."""
    test_cases = [
        (19, 1, "Wild Card"),
        (20, 2, "Divisional"),
        (21, 3, "Conference"),
        (22, 4, "Super Bowl")
    ]

    for api_week, expected_pst_week, round_name in test_cases:
        request_data = {
            "params": {
                "week_sequence": api_week,
                "api_season_type": "REG"  # API might lag
            }
        }

        result = detect_season_type(request_data)

        assert result['status'] == True
        assert result['data']['season_type'] == 'PST'
        assert result['data']['week_sequence'] == api_week  # Original week
        assert result['data']['pst_week'] == expected_pst_week  # Converted week
        print(f"✓ PST week conversion: week {api_week} → PST week {expected_pst_week} ({round_name})")


def test_regular_season_pst_week_equals_sequence():
    """Test that pst_week equals week_sequence for REG season."""
    request_data = {
        "params": {
            "week_sequence": 10,
            "api_season_type": "REG"
        }
    }

    result = detect_season_type(request_data)

    assert result['status'] == True
    assert result['data']['season_type'] == 'REG'
    assert result['data']['week_sequence'] == 10
    assert result['data']['pst_week'] == 10  # Same for REG
    print("✓ REG season: pst_week equals week_sequence")


def run_all_tests():
    """Run all test functions."""
    tests = [
        test_preseason,
        test_regular_season,
        test_playoffs_correction,
        test_current_scenario,
        test_wild_card_round,
        test_missing_week,
        test_season_year_january,
        test_season_year_july,
        test_season_year_august,
        test_season_year_december,
        test_season_year_always_present,
        test_pst_week_conversion,
        test_regular_season_pst_week_equals_sequence
    ]

    passed = 0
    failed = 0

    for test_func in tests:
        try:
            test_func()
            passed += 1
        except AssertionError as e:
            print(f"✗ {test_func.__name__} failed: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {test_func.__name__} error: {e}")
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

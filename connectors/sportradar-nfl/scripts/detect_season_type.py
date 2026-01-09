"""
Detect NFL season type based on week sequence and current date.

Logic:
- PRE: Weeks 0-4 (Preseason)
- REG: Weeks 1-18 (Regular season)
- PST: Weeks 19+ OR date after regular season end (Playoffs/Postseason)

NFL Season Calendar (approximate):
- Regular season: September - early January (18 weeks)
- Playoffs: Mid-January - early February (4 weeks)
- Super Bowl: Early February
"""

from datetime import datetime


def detect_season_type(request_data):
    """
    Detect the correct NFL season type and year.

    Season Type Rules:
    - Week >= 19: Always PST (Playoffs)
    - Week 18 + date >= Jan 6: PST (Playoff start with API lag)
    - All other cases: Trust API (PRE/REG)

    Season Year Rules:
    - Jan-Jul: Previous year (e.g., Jan 2026 → 2025 season)
    - Aug-Dec: Current year (e.g., Sep 2026 → 2026 season)

    Args:
        request_data: Dictionary with params containing:
            - week_sequence: Week number from API
            - api_season_type: Season type returned by API (may be incorrect)

    Returns:
        Dictionary with status, message, and data containing:
            - season_type (str): Corrected season type (PRE/REG/PST)
            - season_year (int): Calculated NFL season year
            - week_sequence (int): Original week number from API
            - pst_week (int): Week number adjusted for PST (19→1, 20→2, etc.)
            - api_season_type (str): Original API value
            - corrected (bool): Whether season_type was corrected
            - reason (str): Explanation of detection logic
            - detection_date (str): Date used for calculation
    """
    params = request_data.get("params", {})

    week_sequence = params.get('week_sequence')
    api_season_type = params.get('api_season_type', 'REG')

    # Validate week_sequence
    if week_sequence is None:
        return {
            "status": False,
            "message": "week_sequence is required",
            "data": {'season_type': api_season_type}
        }

    try:
        week_num = int(week_sequence)
    except (ValueError, TypeError):
        return {
            "status": False,
            "message": f"Invalid week_sequence: {week_sequence}",
            "data": {'season_type': api_season_type}
        }

    # Get current date
    current_date = datetime.now()
    current_month = current_date.month
    current_day = current_date.day
    current_year = current_date.year

    # Calculate season year based on month
    # NFL season runs Sep-Feb, so Jan-Jul belongs to previous year's season
    if current_month >= 8:  # August-December
        season_year = current_year
    else:  # January-July
        season_year = current_year - 1

    # Determine season type based on week number and date
    # Note: Preseason typically uses different week numbering in API

    # Primary check: Week >= 19 is always playoffs
    if week_num >= 19:
        detected_type = 'PST'
        reason = f"week >= 19"
    # Secondary check: Week 18 + date after Jan 6 = playoffs started
    elif week_num == 18 and current_month == 1 and current_day >= 6:
        detected_type = 'PST'
        reason = f"week 18 after Jan 6 (playoffs started)"
    else:
        # For all other cases, trust API or default to REG
        detected_type = api_season_type if api_season_type in ['PRE', 'REG'] else 'REG'
        reason = "using API value"

    # Check if correction was needed
    corrected = detected_type != api_season_type

    # Convert week number for PST (playoffs use weeks 1-5, not 19-23)
    if detected_type == 'PST':
        pst_week = week_num - 18  # week 19 → 1, week 20 → 2, etc.
    else:
        pst_week = week_num

    return {
        "status": True,
        "message": f"Season detection: {season_year} {detected_type} Week {week_num} (PST week {pst_week if detected_type == 'PST' else 'N/A'}) ({reason})" +
                   (f" - corrected from {api_season_type}" if corrected else ""),
        "data": {
            'season_type': detected_type,
            'season_year': season_year,
            'week_sequence': week_num,
            'pst_week': pst_week,
            'api_season_type': api_season_type,
            'corrected': corrected,
            'reason': reason,
            'detection_date': current_date.strftime('%Y-%m-%d')
        }
    }

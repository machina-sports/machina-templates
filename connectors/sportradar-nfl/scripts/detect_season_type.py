"""
Detect NFL season type based on week sequence and current date.

Logic:
- PRE: Weeks 0-4 (Preseason)
- REG: Weeks 1-18 (Regular season)
- PST: Weeks 19+ (Playoffs/Postseason)
"""

from datetime import datetime


def detect_season_type(request_data):
    """
    Detect the correct NFL season type.

    Args:
        request_data: Dictionary with params containing:
            - week_sequence: Week number from API
            - api_season_type: Season type returned by API (may be incorrect)

    Returns:
        Dictionary with status, message, and corrected season_type
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

    # Determine season type based on week number
    # Note: Preseason typically uses different week numbering in API
    # Focus on detecting playoffs (PST) when week >= 19
    if week_num >= 19:
        detected_type = 'PST'
    else:
        # For weeks 1-18, trust API or default to REG
        detected_type = api_season_type if api_season_type in ['PRE', 'REG'] else 'REG'

    # Check if correction was needed
    corrected = detected_type != api_season_type

    return {
        "status": True,
        "message": f"Season type detected: {detected_type}" +
                   (f" (corrected from {api_season_type})" if corrected else ""),
        "data": {
            'season_type': detected_type,
            'week_sequence': week_num,
            'api_season_type': api_season_type,
            'corrected': corrected
        }
    }

def invoke_get_current_season(request_data):

    params = request_data.get("params", {})

    seasons_data = params.get("seasons", [])

    if not seasons_data:
        return {
            "status": False,
            "message": "No seasons data provided.",
            "data": {"current-season": None},
        }

    from datetime import datetime

    # Get current date
    today = datetime.now().date()

    # Find active seasons (where today is between start_date and end_date)
    current_seasons = []
    for season in seasons_data:
        try:
            start_date = datetime.fromisoformat(season.get("start_date", "")).date()
            end_date = datetime.fromisoformat(season.get("end_date", "")).date()

            print(f"Start Date: {start_date}, End Date: {end_date}, Today: {today}")

            if start_date <= today <= end_date:
                current_seasons.append(season)
        except (ValueError, TypeError):
            # Skip seasons with invalid dates
            continue

    # If no active season found, get the next upcoming season or most recent past season
    if not current_seasons:
        try:
            # First try to find upcoming seasons (start_date > today)
            upcoming_seasons = []
            past_seasons = []

            for season in seasons_data:
                start_date = datetime.fromisoformat(
                    season.get("start_date", "1900-01-01")
                ).date()
                if start_date > today:
                    upcoming_seasons.append(season)
                else:
                    past_seasons.append(season)

            # If there are upcoming seasons, get the next one
            if upcoming_seasons:
                current_seasons = sorted(
                    upcoming_seasons,
                    key=lambda s: datetime.fromisoformat(
                        s.get("start_date", "1900-01-01")
                    ).date(),
                )[:1]
            # Otherwise, get the most recent past season
            elif past_seasons:
                current_seasons = sorted(
                    past_seasons,
                    key=lambda s: datetime.fromisoformat(
                        s.get("start_date", "1900-01-01")
                    ).date(),
                    reverse=True,
                )[:1]
        except (ValueError, TypeError):
            current_seasons = []

    current_season = current_seasons[0] if current_seasons else None

    return {
        "status": True,
        "message": f"Current season found: {current_season.get('name', 'Unknown') if current_season else 'None'}",
        "data": {"current-season": current_season},
    }

import requests
import json
import gzip
from io import BytesIO

BASE_URL = "https://www.goalserve.com/getfeed"
INPLAY_URL = "http://inplay.goalserve.com"


def get_leagues_mapping(request_data):
    """
    Get list of all available soccer leagues from Goalserve.

    Args:
        request_data (dict): Dictionary containing:
            - params (dict): Dictionary with:
                - api_key (str, required): Goalserve API key

    Returns:
        dict: Status and leagues data
    """
    params = request_data.get("params", {})
    api_key = params.get("api_key")

    if not api_key:
        return {"status": False, "message": "API key is required"}

    url = f"{BASE_URL}/{api_key}/soccerfixtures/data/mapping"

    try:
        response = requests.get(url, params={"json": 1}, timeout=30)
        response.raise_for_status()

        data = response.json()
        return {"status": True, "data": data}

    except requests.exceptions.RequestException as e:
        return {"status": False, "message": f"Request failed: {str(e)}"}
    except json.JSONDecodeError as e:
        return {"status": False, "message": f"JSON decode error: {str(e)}", "raw_response": response.text[:500]}


def get_livescores(request_data):
    """
    Get live soccer scores from Goalserve.

    Args:
        request_data (dict): Dictionary containing:
            - params (dict): Dictionary with:
                - api_key (str, required): Goalserve API key
                - day (str, optional): Day selector - home, live, d1, d2, d3, d-1, d-2, d-3. Default: home
                - cat (str, optional): League/category ID filter

    Returns:
        dict: Status and livescores data
    """
    params = request_data.get("params", {})
    api_key = params.get("api_key")
    day = params.get("day", "home")
    cat = params.get("cat")

    if not api_key:
        return {"status": False, "message": "API key is required"}

    url = f"{BASE_URL}/{api_key}/soccernew/{day}"

    query_params = {"json": 1}
    if cat:
        query_params["cat"] = cat

    try:
        response = requests.get(url, params=query_params, timeout=30)
        response.raise_for_status()

        data = response.json()
        return {"status": True, "data": data}

    except requests.exceptions.RequestException as e:
        return {"status": False, "message": f"Request failed: {str(e)}"}
    except json.JSONDecodeError as e:
        return {"status": False, "message": f"JSON decode error: {str(e)}", "raw_response": response.text[:500]}


def get_standings(request_data):
    """
    Get league standings from Goalserve.

    Args:
        request_data (dict): Dictionary containing:
            - params (dict): Dictionary with:
                - api_key (str, required): Goalserve API key
                - league_id (str, required): League ID
                - season (str, optional): Season year

    Returns:
        dict: Status and standings data
    """
    params = request_data.get("params", {})
    api_key = params.get("api_key")
    league_id = params.get("league_id")
    season = params.get("season")

    if not api_key:
        return {"status": False, "message": "API key is required"}

    if not league_id:
        return {"status": False, "message": "League ID is required"}

    url = f"{BASE_URL}/{api_key}/standings/{league_id}.xml"

    query_params = {"json": 1}
    if season:
        query_params["season"] = season

    try:
        response = requests.get(url, params=query_params, timeout=30)
        response.raise_for_status()

        data = response.json()
        return {"status": True, "data": data}

    except requests.exceptions.RequestException as e:
        return {"status": False, "message": f"Request failed: {str(e)}"}
    except json.JSONDecodeError as e:
        return {"status": False, "message": f"JSON decode error: {str(e)}", "raw_response": response.text[:500]}


def get_topscorers(request_data):
    """
    Get league top scorers from Goalserve.

    Args:
        request_data (dict): Dictionary containing:
            - params (dict): Dictionary with:
                - api_key (str, required): Goalserve API key
                - league_id (str, required): League ID

    Returns:
        dict: Status and top scorers data
    """
    params = request_data.get("params", {})
    api_key = params.get("api_key")
    league_id = params.get("league_id")

    if not api_key:
        return {"status": False, "message": "API key is required"}

    if not league_id:
        return {"status": False, "message": "League ID is required"}

    url = f"{BASE_URL}/{api_key}/topscorers/{league_id}"

    try:
        response = requests.get(url, params={"json": 1}, timeout=30)
        response.raise_for_status()

        data = response.json()
        return {"status": True, "data": data}

    except requests.exceptions.RequestException as e:
        return {"status": False, "message": f"Request failed: {str(e)}"}
    except json.JSONDecodeError as e:
        return {"status": False, "message": f"JSON decode error: {str(e)}", "raw_response": response.text[:500]}


def get_pregame_odds(request_data):
    """
    Get pregame odds from multiple bookmakers.

    Args:
        request_data (dict): Dictionary containing:
            - params (dict): Dictionary with:
                - api_key (str, required): Goalserve API key
                - cat (str, optional): Category - soccer_10, basket_10, etc. Default: soccer_10
                - date_start (str, optional): Start date filter (dd.MM.yyyy)
                - date_end (str, optional): End date filter (dd.MM.yyyy)
                - bm (str, optional): Bookmaker filter (comma separated)
                - market (str, optional): Market filter (comma separated)
                - league (str, optional): League ID filter (comma separated)
                - match (str, optional): Match ID filter (comma separated)
                - ts (str, optional): Timestamp for incremental updates

    Returns:
        dict: Status and odds data
    """
    params = request_data.get("params", {})
    api_key = params.get("api_key")
    cat = params.get("cat", "soccer_10")

    if not api_key:
        return {"status": False, "message": "API key is required"}

    url = f"{BASE_URL}/{api_key}/getodds/soccer"

    query_params = {"json": 1, "cat": cat}

    # Optional filters
    if params.get("date_start"):
        query_params["date_start"] = params["date_start"]
    if params.get("date_end"):
        query_params["date_end"] = params["date_end"]
    if params.get("bm"):
        query_params["bm"] = params["bm"]
    if params.get("market"):
        query_params["market"] = params["market"]
    if params.get("league"):
        query_params["league"] = params["league"]
    if params.get("match"):
        query_params["match"] = params["match"]
    if params.get("ts"):
        query_params["ts"] = params["ts"]

    try:
        response = requests.get(url, params=query_params, timeout=60)
        response.raise_for_status()

        data = response.json()
        return {"status": True, "data": data}

    except requests.exceptions.RequestException as e:
        return {"status": False, "message": f"Request failed: {str(e)}"}
    except json.JSONDecodeError as e:
        return {"status": False, "message": f"JSON decode error: {str(e)}", "raw_response": response.text[:500]}


def get_fixtures(request_data):
    """
    Get full season fixtures for a league.

    Args:
        request_data (dict): Dictionary containing:
            - params (dict): Dictionary with:
                - api_key (str, required): Goalserve API key
                - league_id (str, required): League ID

    Returns:
        dict: Status and fixtures data
    """
    params = request_data.get("params", {})
    api_key = params.get("api_key")
    league_id = params.get("league_id")

    if not api_key:
        return {"status": False, "message": "API key is required"}

    if not league_id:
        return {"status": False, "message": "League ID is required"}

    url = f"{BASE_URL}/{api_key}/soccerfixtures/leagueid/{league_id}"

    try:
        response = requests.get(url, params={"json": 1}, timeout=30)
        response.raise_for_status()

        data = response.json()
        return {"status": True, "data": data}

    except requests.exceptions.RequestException as e:
        return {"status": False, "message": f"Request failed: {str(e)}"}
    except json.JSONDecodeError as e:
        return {"status": False, "message": f"JSON decode error: {str(e)}", "raw_response": response.text[:500]}


def get_seasons(request_data):
    """
    Get list of available seasons for all leagues.

    Args:
        request_data (dict): Dictionary containing:
            - params (dict): Dictionary with:
                - api_key (str, required): Goalserve API key

    Returns:
        dict: Status and seasons data
    """
    params = request_data.get("params", {})
    api_key = params.get("api_key")

    if not api_key:
        return {"status": False, "message": "API key is required"}

    url = f"{BASE_URL}/{api_key}/soccerfixtures/data/seasons"

    try:
        response = requests.get(url, params={"json": 1}, timeout=30)
        response.raise_for_status()

        data = response.json()
        return {"status": True, "data": data}

    except requests.exceptions.RequestException as e:
        return {"status": False, "message": f"Request failed: {str(e)}"}
    except json.JSONDecodeError as e:
        return {"status": False, "message": f"JSON decode error: {str(e)}", "raw_response": response.text[:500]}


def get_inplay_odds(request_data):
    """
    Get live inplay odds (refreshes every second).
    Note: This endpoint returns gzipped JSON data.

    Args:
        request_data (dict): Dictionary containing:
            - params (dict): Dictionary with:
                - sport (str, optional): Sport type - soccer, basket, tennis, etc. Default: soccer

    Returns:
        dict: Status and inplay odds data
    """
    params = request_data.get("params", {})
    sport = params.get("sport", "soccer")

    url = f"{INPLAY_URL}/inplay-{sport}.gz"

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        # Decompress gzip data
        compressed_data = BytesIO(response.content)
        with gzip.GzipFile(fileobj=compressed_data) as f:
            decompressed_data = f.read().decode('utf-8')

        data = json.loads(decompressed_data)
        return {"status": True, "data": data}

    except requests.exceptions.RequestException as e:
        return {"status": False, "message": f"Request failed: {str(e)}"}
    except (gzip.BadGzipFile, json.JSONDecodeError) as e:
        return {"status": False, "message": f"Data decode error: {str(e)}"}


def get_inplay_mapping(request_data):
    """
    Get inplay odds mapping with pregame stats feed.

    Args:
        request_data (dict): Dictionary containing:
            - params (dict): Dictionary with:
                - api_key (str, required): Goalserve API key

    Returns:
        dict: Status and inplay mapping data
    """
    params = request_data.get("params", {})
    api_key = params.get("api_key")

    if not api_key:
        return {"status": False, "message": "API key is required"}

    url = f"{BASE_URL}/{api_key}/soccernew/inplay-mapping"

    try:
        response = requests.get(url, params={"json": 1}, timeout=30)
        response.raise_for_status()

        data = response.json()
        return {"status": True, "data": data}

    except requests.exceptions.RequestException as e:
        return {"status": False, "message": f"Request failed: {str(e)}"}
    except json.JSONDecodeError as e:
        return {"status": False, "message": f"JSON decode error: {str(e)}", "raw_response": response.text[:500]}


def get_live_stats(request_data):
    """
    Get live match statistics and lineups (commentaries).

    Args:
        request_data (dict): Dictionary containing:
            - params (dict): Dictionary with:
                - api_key (str, required): Goalserve API key
                - league_id (str, required): League ID
                - date (str, optional): Date for past game stats (dd.MM.yyyy)

    Returns:
        dict: Status and live stats data
    """
    params = request_data.get("params", {})
    api_key = params.get("api_key")
    league_id = params.get("league_id")
    date = params.get("date")

    if not api_key:
        return {"status": False, "message": "API key is required"}

    if not league_id:
        return {"status": False, "message": "League ID is required"}

    url = f"{BASE_URL}/{api_key}/commentaries/{league_id}.xml"

    query_params = {"json": 1}
    if date:
        query_params["date"] = date

    try:
        response = requests.get(url, params=query_params, timeout=30)
        response.raise_for_status()

        data = response.json()
        return {"status": True, "data": data}

    except requests.exceptions.RequestException as e:
        return {"status": False, "message": f"Request failed: {str(e)}"}
    except json.JSONDecodeError as e:
        return {"status": False, "message": f"JSON decode error: {str(e)}", "raw_response": response.text[:500]}


def get_match_stats(request_data):
    """
    Get statistics for a specific match.

    Args:
        request_data (dict): Dictionary containing:
            - params (dict): Dictionary with:
                - api_key (str, required): Goalserve API key
                - match_id (str, required): Match static ID
                - league_id (str, required): League ID

    Returns:
        dict: Status and match stats data
    """
    params = request_data.get("params", {})
    api_key = params.get("api_key")
    match_id = params.get("match_id")
    league_id = params.get("league_id")

    if not api_key:
        return {"status": False, "message": "API key is required"}

    if not match_id:
        return {"status": False, "message": "Match ID is required"}

    if not league_id:
        return {"status": False, "message": "League ID is required"}

    url = f"{BASE_URL}/{api_key}/commentaries/match"

    try:
        response = requests.get(url, params={"json": 1, "id": match_id, "league": league_id}, timeout=30)
        response.raise_for_status()

        data = response.json()
        return {"status": True, "data": data}

    except requests.exceptions.RequestException as e:
        return {"status": False, "message": f"Request failed: {str(e)}"}
    except json.JSONDecodeError as e:
        return {"status": False, "message": f"JSON decode error: {str(e)}", "raw_response": response.text[:500]}


def get_historical(request_data):
    """
    Get historical fixtures and results from past seasons.

    Args:
        request_data (dict): Dictionary containing:
            - params (dict): Dictionary with:
                - api_key (str, required): Goalserve API key
                - league_id (str, required): League ID
                - season (str, required): Season in format "YYYY-YYYY" (e.g., "2023-2024")

    Returns:
        dict: Status and historical data
    """
    params = request_data.get("params", {})
    api_key = params.get("api_key")
    league_id = params.get("league_id")
    season = params.get("season")

    if not api_key:
        return {"status": False, "message": "API key is required"}

    if not league_id:
        return {"status": False, "message": "League ID is required"}

    if not season:
        return {"status": False, "message": "Season is required (format: YYYY-YYYY)"}

    url = f"{BASE_URL}/{api_key}/soccerhistory/leagueid/{league_id}-{season}"

    try:
        response = requests.get(url, params={"json": 1}, timeout=30)
        response.raise_for_status()

        data = response.json()
        return {"status": True, "data": data}

    except requests.exceptions.RequestException as e:
        return {"status": False, "message": f"Request failed: {str(e)}"}
    except json.JSONDecodeError as e:
        return {"status": False, "message": f"JSON decode error: {str(e)}", "raw_response": response.text[:500]}


def get_inplay_match_result(request_data):
    """
    Get match result by ID (used to calculate inplay odds winning).
    Results are available after game end.

    Args:
        request_data (dict): Dictionary containing:
            - params (dict): Dictionary with:
                - match_id (str, required): Match ID
                - year_month (str, required): Year and month in format "YYYYMM" (e.g., "202104")

    Returns:
        dict: Status and match result data
    """
    params = request_data.get("params", {})
    match_id = params.get("match_id")
    year_month = params.get("year_month")

    if not match_id:
        return {"status": False, "message": "Match ID is required"}

    if not year_month:
        return {"status": False, "message": "Year/month is required (format: YYYYMM)"}

    url = f"{INPLAY_URL}/results/{year_month}/{match_id}.json"

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()

        data = response.json()
        return {"status": True, "data": data}

    except requests.exceptions.RequestException as e:
        return {"status": False, "message": f"Request failed: {str(e)}"}
    except json.JSONDecodeError as e:
        return {"status": False, "message": f"JSON decode error: {str(e)}", "raw_response": response.text[:500]}

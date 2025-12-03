import requests
import json
import traceback

# Base URL for Kalshi API (public unauthenticated access)
# Note: 'api.elections.kalshi.com' works for all markets, not just elections.
BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"

def get_series(params):
    """
    Get series information.
    Params:
        series_ticker (str): The ticker symbol for the series (e.g., "KXHIGHNY").
    """
    try:
        series_ticker = params.get("series_ticker")
        if not series_ticker:
            return {"status": False, "message": "series_ticker is required."}

        url = f"{BASE_URL}/series/{series_ticker}"
        print(f"Fetching series info from: {url}")
        
        response = requests.get(url)
        response.raise_for_status()
        
        return {
            "status": True, 
            "data": response.json(), 
            "message": f"Series {series_ticker} retrieved successfully."
        }

    except Exception as e:
        print(f"Error fetching series {series_ticker}: {str(e)}")
        print(traceback.format_exc())
        return {"status": False, "message": f"Error fetching series: {str(e)}"}

def get_markets(params):
    """
    Get markets.
    Params:
        limit (int): Number of markets to fetch (default 100).
        cursor (str): Pagination cursor.
        event_ticker (str): Filter by event ticker.
        series_ticker (str): Filter by series ticker.
        status (str): Filter by status (e.g., "open", "closed").
        tickers (str): Comma-separated list of market tickers.
    """
    try:
        query_params = {
            "limit": params.get("limit", 100),
            "cursor": params.get("cursor"),
            "event_ticker": params.get("event_ticker"),
            "series_ticker": params.get("series_ticker"),
            "status": params.get("status", "open"),
            "tickers": params.get("tickers")
        }
        
        # Remove None values
        query_params = {k: v for k, v in query_params.items() if v is not None}
        
        url = f"{BASE_URL}/markets"
        print(f"Fetching markets from: {url} with params: {query_params}")
        
        response = requests.get(url, params=query_params)
        response.raise_for_status()
        
        return {
            "status": True, 
            "data": response.json(), 
            "message": "Markets retrieved successfully."
        }
        
    except Exception as e:
        print(f"Error fetching markets: {str(e)}")
        print(traceback.format_exc())
        return {"status": False, "message": f"Error fetching markets: {str(e)}"}

def get_events(params):
    """
    Get event details.
    Params:
        event_ticker (str): The ticker symbol for the event.
        limit (int): Limit for list events if no ticker provided.
        cursor (str): Pagination cursor.
        status (str): Filter by status.
        series_ticker (str): Filter by series.
    """
    try:
        event_ticker = params.get("event_ticker")
        
        if event_ticker:
            # Get specific event
            url = f"{BASE_URL}/events/{event_ticker}"
            print(f"Fetching event info from: {url}")
            response = requests.get(url)
        else:
            # List events
            url = f"{BASE_URL}/events"
            query_params = {
                "limit": params.get("limit", 100),
                "cursor": params.get("cursor"),
                "status": params.get("status"),
                "series_ticker": params.get("series_ticker")
            }
            # Remove None values
            query_params = {k: v for k, v in query_params.items() if v is not None}
            print(f"Fetching events list from: {url} with params: {query_params}")
            response = requests.get(url, params=query_params)

        response.raise_for_status()
        
        return {
            "status": True, 
            "data": response.json(), 
            "message": "Events retrieved successfully."
        }

    except Exception as e:
        print(f"Error fetching events: {str(e)}")
        print(traceback.format_exc())
        return {"status": False, "message": f"Error fetching events: {str(e)}"}

def get_orderbook(params):
    """
    Get orderbook for a specific market.
    Params:
        market_ticker (str): The ticker symbol for the market.
    """
    try:
        market_ticker = params.get("market_ticker")
        if not market_ticker:
            return {"status": False, "message": "market_ticker is required."}

        url = f"{BASE_URL}/markets/{market_ticker}/orderbook"
        print(f"Fetching orderbook from: {url}")
        
        response = requests.get(url)
        response.raise_for_status()
        
        return {
            "status": True, 
            "data": response.json(), 
            "message": f"Orderbook for {market_ticker} retrieved successfully."
        }

    except Exception as e:
        print(f"Error fetching orderbook for {market_ticker}: {str(e)}")
        print(traceback.format_exc())
        return {"status": False, "message": f"Error fetching orderbook: {str(e)}"}


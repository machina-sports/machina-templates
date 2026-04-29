import hashlib
import requests
import time


def authorization(request_data):
    """
    Authenticate with Opta OAuth API and return access token
    
    Args:
        request_data: Dictionary containing:
            - headers: {'outlet': str, 'secret': str}
        
    Returns:
        Dictionary with status and access_token or error message
    """
    try:
        headers = request_data.get("headers", {})
        outlet = headers.get("outlet")
        secret = headers.get("secret")
        
        if not outlet or not secret:
            return {
                "status": False,
                "message": "Both 'outlet' and 'secret' are required in headers.",
                "data": {}
            }
        
        # Generate timestamp
        timestamp = int(round(time.time() * 1000))
        
        # Generate unique hash
        key = str.encode(outlet + str(timestamp) + secret)
        unique_hash = hashlib.sha512(key).hexdigest()
        
        # Prepare OAuth request
        post_url = f"https://oauth.performgroup.com/oauth/token/{outlet}?_fmt=json&_rt=b"
        
        auth_headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': f'Basic {unique_hash}',
            'Timestamp': str(timestamp)
        }
        
        body = {
            'grant_type': 'client_credentials',
            'scope': 'b2b-feeds-auth'
        }
        
        # Call OAuth API
        response = requests.post(post_url, data=body, headers=auth_headers)
        
        if response.status_code != 200:
            return {
                "status": False,
                "message": f"OAuth authentication failed with status {response.status_code}",
                "data": {"details": response.text}
            }
        
        response_data = response.json()
        access_token = response_data.get('access_token')
        
        if not access_token:
            return {
                "status": False,
                "message": "No access token in OAuth response",
                "data": {"details": response_data}
            }
        
        return {
            "status": True,
            "message": "Authentication successful",
            "data": {
                "access_token": access_token,
                "token_data": response_data
            }
        }
        
    except Exception as e:
        return {
            "status": False,
            "message": f"Exception during authorization: {str(e)}",
            "data": {}
        }


def invoke_request(request_data):
    """
    Make authenticated request to Opta SDAPI
    
    Args:
        request_data: Dictionary containing:
            - headers: {'outlet': str}
            - params: {
                'access_token': str (required, from authorization function),
                'endpoint': str (e.g., 'tournamentcalendar', 'match', etc.),
                'competition_id': str (optional, e.g., '2kwbbcootiqqgmrzs6o5inle5'),
                'query_params': dict (optional, additional query parameters)
              }
              
    Returns:
        Dictionary with status and API response data
    """
    # Known Opta API error codes
    OPTA_ERROR_CODES = {
        "10201": "Access denied or invalid parameters. Check: 1) Outlet has access to this competition/season, 2) Competition ID and Season ID are valid, 3) Endpoint is available for your subscription",
        "10203": "Invalid or missing required parameters. Check parameter names (e.g., strtDt not strDt) and format",
        "10001": "Authentication failed - invalid credentials",
        "10002": "Invalid or expired access token",
        "10003": "Missing required parameters",
        "10004": "Invalid parameter format",
        "10005": "Rate limit exceeded",
        "10101": "Resource not found",
        "10102": "Competition not available for outlet",
    }
    
    api_url = None  # Initialize for error reporting
    
    try:
        headers = request_data.get("headers", {})
        params = request_data.get("params", {})
        
        # Get outlet and access token
        outlet = headers.get("outlet")
        access_token = params.get("access_bearer") or params.get("access_token")
        
        if not outlet:
            return {
                "status": False,
                "message": "'outlet' is required in headers.",
                "data": {"debug": {"provided_headers": headers}}
            }
        
        if not access_token:
            return {
                "status": False,
                "message": "'access_token' is required in params. Call authorization first.",
                "data": {"debug": {"params_keys": list(params.keys())}}
            }
        
        # Get endpoint parameters
        endpoint = params.get("endpoint", "tournamentcalendar")
        competition_id = params.get("competition_id")
        query_params = params.get("query_params", {})
        
        # Build API URL - some endpoints require IDs in path
        if endpoint == "tournamentschedule" and query_params.get("seasonId"):
            # For tournamentschedule, season ID goes in the URL path
            season_id = query_params.pop("seasonId")
            base_url = f"https://api.performfeeds.com/soccerdata/{endpoint}/{outlet}/{season_id}"
        elif endpoint in ["matchstats", "matchexpectedgoals"] and query_params.get("matchId"):
            # For matchstats and matchexpectedgoals, match ID goes in the URL path
            match_id = query_params.pop("matchId")
            base_url = f"https://api.performfeeds.com/soccerdata/{endpoint}/{outlet}/{match_id}"
        else:
            base_url = f"https://api.performfeeds.com/soccerdata/{endpoint}/{outlet}"
        
        # Build query string
        query_parts = ["_rt=b", "_fmt=json"]
        
        # For tournamentschedule, competition ID is NOT needed in query params
        if competition_id and endpoint != "tournamentschedule":
            query_parts.append(f"comp={competition_id}")
        
        # Add any additional query parameters
        for key, value in query_params.items():
            if value is not None:  # Only add params that have values
                query_parts.append(f"{key}={value}")
        
        api_url = f"{base_url}?{'&'.join(query_parts)}"
        
        # Debug logging
        print(f"[DEBUG] Making request to: {api_url}")
        print(f"[DEBUG] Endpoint: {endpoint}")
        print(f"[DEBUG] Competition ID: {competition_id}")
        print(f"[DEBUG] Query params dict: {query_params}")
        print(f"[DEBUG] Query parts: {query_parts}")
        
        # Make API request
        response = requests.get(api_url, headers={'Authorization': f'Bearer {access_token}'})
        
        print(f"[DEBUG] Response status code: {response.status_code}")
        
        if response.status_code != 200:
            error_details = {
                "status_code": response.status_code,
                "response_text": response.text,
                "url_called": api_url,
                "endpoint": endpoint,
                "competition_id": competition_id,
                "query_params": query_params,
                "outlet": outlet
            }
            
            # Try to parse error response as JSON and decode error code
            error_message = response.text[:200]
            try:
                error_json = response.json()
                error_details["error_json"] = error_json
                
                # Check for error code and decode it
                if "errorCode" in error_json:
                    error_code = error_json["errorCode"]
                    decoded_message = OPTA_ERROR_CODES.get(error_code, f"Unknown error code: {error_code}")
                    error_details["decoded_error"] = decoded_message
                    error_message = f"Error {error_code}: {decoded_message}"
                    print(f"[ERROR] Opta Error Code: {error_code} - {decoded_message}")
            except:
                pass
            
            print(f"[ERROR] Response text: {response.text[:500]}")
            
            return {
                "status": False,
                "message": f"API request failed with status {response.status_code}: {error_message}",
                "data": error_details
            }
        
        # Parse response
        response_data = response.json()
        
        print(f"[DEBUG] Successfully fetched data from {endpoint}")
        print(f"[DEBUG] Response keys: {list(response_data.keys()) if isinstance(response_data, dict) else 'Not a dict'}")
        
        return {
            "status": True,
            "message": f"Successfully fetched data from {endpoint}",
            "data": response_data
        }
        
    except requests.exceptions.RequestException as e:
        error_details = {
            "exception_type": "RequestException",
            "exception_message": str(e),
            "url_called": api_url
        }
        return {
            "status": False,
            "message": f"Request exception: {str(e)}",
            "data": error_details
        }
    except Exception as e:
        error_details = {
            "exception_type": type(e).__name__,
            "exception_message": str(e),
            "url_called": api_url
        }
        return {
            "status": False,
            "message": f"Exception during API request: {type(e).__name__}: {str(e)}",
            "data": error_details
        }

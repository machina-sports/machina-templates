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
    try:
        headers = request_data.get("headers", {})
        params = request_data.get("params", {})
        
        # Get outlet and access token
        outlet = headers.get("outlet")
        access_token = params.get("access_token")
        
        if not outlet:
            return {
                "status": False,
                "message": "'outlet' is required in headers.",
                "data": {}
            }
        
        if not access_token:
            return {
                "status": False,
                "message": "'access_token' is required in params. Call authorization first.",
                "data": {}
            }
        
        # Get endpoint parameters
        endpoint = params.get("endpoint", "tournamentcalendar")
        competition_id = params.get("competition_id")
        query_params = params.get("query_params", {})
        
        # Build API URL
        base_url = f"https://api.performfeeds.com/soccerdata/{endpoint}/{outlet}"
        
        # Build query string
        query_parts = ["_rt=b", "_fmt=json"]
        
        if competition_id:
            query_parts.append(f"comp={competition_id}")
        
        # Add any additional query parameters
        for key, value in query_params.items():
            query_parts.append(f"{key}={value}")
        
        api_url = f"{base_url}?{'&'.join(query_parts)}"
        
        # Make API request
        api_headers = {
            'Authorization': f'Bearer {access_token}'
        }
        
        response = requests.get(api_url, headers=api_headers)
        
        if response.status_code != 200:
            return {
                "status": False,
                "message": f"API request failed with status {response.status_code}",
                "data": {"details": response.text}
            }
        
        # Parse response
        response_data = response.json()
        
        return {
            "status": True,
            "message": f"Successfully fetched data from {endpoint}",
            "data": response_data
        }
        
    except requests.exceptions.RequestException as e:
        return {
            "status": False,
            "message": f"Request exception: {str(e)}",
            "data": {}
        }
    except Exception as e:
        return {
            "status": False,
            "message": f"Exception during API request: {str(e)}",
            "data": {}
        }

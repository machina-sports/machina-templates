import requests
import base64


def list_articles(request_data):
    """
    Retrieve articles from Zendesk Help Center
    
    Args:
        request_data: Dictionary containing:
            - headers: {'username': str, 'password': str}
            - params: {
                'locale': str (e.g., 'en-gb'),
                'sort_by': str (optional, default: 'updated_at'),
                'sort_order': str (optional, default: 'asc'),
                'page': int (optional, default: 1),
                'per_page': int (optional, default: 30)
              }
    
    Returns:
        Dictionary with articles response or error message
    """
    try:
        # Get headers and params
        headers = request_data.get("headers", {})
        params = request_data.get("params", {})
        
        username = headers.get("username") or ""
        password = headers.get("password") or ""
        
        # Strip whitespace and check if empty
        username = username.strip() if username else ""
        password = password.strip() if password else ""
        
        if not username or not password:
            return {
                "status": False,
                "message": f"Both 'username' and 'password' are required. Received keys: {list(request_data.keys())}, headers keys: {list(headers.keys()) if headers else 'None'}",
                "data": {"request_data_keys": list(request_data.keys())}
            }
        
        # Build Basic Auth header
        credentials = f"{username}:{password}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        auth_header = f"Basic {encoded_credentials}"
        
        # Get parameters
        locale = params.get("locale", "en-gb")
        sort_by = params.get("sort_by", "updated_at")
        sort_order = params.get("sort_order", "asc")
        page = params.get("page", 1)
        per_page = params.get("per_page", 30)
        
        # Build URL
        base_url = "https://bwines.zendesk.com"
        url = f"{base_url}/api/v2/help_center/{locale}/articles"
        
        # Build query parameters
        query_params = {
            "sort_by": sort_by,
            "sort_order": sort_order,
            "page": page,
            "per_page": per_page
        }
        
        # Prepare headers
        request_headers = {
            "Authorization": auth_header,
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        # Make API request
        response = requests.get(url, params=query_params, headers=request_headers)
        
        if response.status_code != 200:
            return {
                "status": False,
                "message": f"Request failed with status {response.status_code}",
                "data": {
                    "status_code": response.status_code,
                    "response_text": response.text[:500] if response.text else None
                }
            }
        
        # Return response data
        response_data = response.json()
        return {
            "status": True,
            "data": response_data
        }
        
    except Exception as e:
        return {
            "status": False,
            "message": f"Error making request: {str(e)}",
            "data": {}
        }


def list_labels(request_data):
    """
    Retrieve labels from Zendesk Help Center
    
    Args:
        request_data: Dictionary containing:
            - headers: {'username': str, 'password': str}
            - params: {} (no parameters needed)
    
    Returns:
        Dictionary with labels response or error message
    """
    try:
        # Get headers and params
        headers = request_data.get("headers", {})
        params = request_data.get("params", {})
        
        username = headers.get("username") or ""
        password = headers.get("password") or ""
        
        # Strip whitespace and check if empty
        username = username.strip() if username else ""
        password = password.strip() if password else ""
        
        if not username or not password:
            return {
                "status": False,
                "message": f"Both 'username' and 'password' are required in context-variables. Username: {'provided' if username else 'MISSING'}, Password: {'provided' if password else 'MISSING'}. Please check MACHINA_CONTEXT_VARIABLE_ZENDESK_USERNAME and MACHINA_CONTEXT_VARIABLE_ZENDESK_PASSWORD environment variables.",
                "data": {
                    "username_provided": bool(username),
                    "password_provided": bool(password),
                    "headers_received": list(headers.keys()) if headers else []
                }
            }
        
        # Build Basic Auth header
        credentials = f"{username}:{password}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        auth_header = f"Basic {encoded_credentials}"
        
        # Build URL
        base_url = "https://bwines.zendesk.com"
        url = f"{base_url}/api/v2/help_center/articles/labels"
        
        # Prepare headers
        request_headers = {
            "Authorization": auth_header,
            "Accept": "application/json",
            "Content-Type": "application/json"
        }
        
        # Make API request
        response = requests.get(url, headers=request_headers)
        
        if response.status_code != 200:
            return {
                "status": False,
                "message": f"Request failed with status {response.status_code}",
                "data": {
                    "status_code": response.status_code,
                    "response_text": response.text[:500] if response.text else None
                }
            }
        
        # Return response data
        response_data = response.json()
        return {
            "status": True,
            "data": response_data
        }
        
    except Exception as e:
        return {
            "status": False,
            "message": f"Error making request: {str(e)}",
            "data": {}
        }


import requests

# Hardcoded values from the user's message
CLIENT_ID = "122672"
CLIENT_SECRET = "Ybvm13115tlSEepRjSm8RwWM41Dt7A0c9iqtfU07EpPOt1c7yL1OINiTw7c7mRZz"
REFRESH_TOKEN = "fKHe72^apfLBH7UQw)Q9&3UHNUzT%W@yw#O$G5&&8SoF((24D$u&&w4#y567zg(f"

def refresh_access_token():
    """Refresh the WordPress.com access token using the refresh token"""
    if not CLIENT_ID or not CLIENT_SECRET or not REFRESH_TOKEN:
        print("Missing client_id, client_secret or refresh_token for refresh")
        return None
        
    print(f"Refreshing token with client_id: {CLIENT_ID}")
    
    body = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": REFRESH_TOKEN,
    }
    
    try:
        resp = requests.post(
            "https://public-api.wordpress.com/oauth2/token",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        
        print(f"Response status: {resp.status_code}")
        
        if resp.status_code >= 400:
            print(f"Refresh failed: {resp.status_code} - {resp.text}")
            return None
            
        payload = resp.json()
        print(f"Refresh successful!")
        print(f"New access token: {payload.get('access_token', '')}")
        print(f"Token type: {payload.get('token_type', '')}")
        print(f"Expires in: {payload.get('expires_in', '')} seconds")
        return payload
    except Exception as e:
        print(f"Exception refreshing token: {e}")
        return None

if __name__ == "__main__":
    print("Attempting to refresh WordPress.com OAuth token...")
    refresh_access_token()

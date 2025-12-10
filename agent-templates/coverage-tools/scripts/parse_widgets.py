def invoke_parse_widgets(request_data):
    """
    Parse and extract specific widgets from Tallysight response.
    Extract Anytime Goalscorer market from the props API response.
    
    Args:
        request_data: Dictionary with params containing widget_embed
        
    Returns:
        Dictionary with extracted widgets
    """
    params = request_data.get("params", {})
    widget_embed = params.get("widget_embed", [])
    
    # Extract Anytime Goalscorer market from the markets array
    anytime_goalscorer_widget = None
    
    if isinstance(widget_embed, list) and len(widget_embed) > 0:
        widget_data = widget_embed[0]
        if isinstance(widget_data, dict):
            markets = widget_data.get('markets', [])
            
            print(f"\n📊 Markets Found: {len(markets)}")
            for market in markets:
                market_name = market.get('name', '')
                if market_name.lower() == 'anytime goalscorer':
                    anytime_goalscorer_widget = market
                    print(f"   ✓ Found: {market_name}")
                    break
    
    print(f"\n🎯 Widget Extraction Results:")
    print(f"   Anytime Goalscorer Market: {'Found' if anytime_goalscorer_widget else 'Not found'}")
    
    return {
        "status": True,
        "message": "Widgets parsed successfully",
        "data": {
            "anytime_goalscorer_widget": anytime_goalscorer_widget
        }
    }


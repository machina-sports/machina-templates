"""
Process markets for article boxes - ONE SINGLE CONNECTOR
"""

def process_markets_for_boxes(request_data):
    """Extract, translate and separate markets by type"""
    
    if not isinstance(request_data, dict):
        return {
            "status": False,
            "error": "Invalid request_data",
            "data": {"markets_3way": [], "markets_over_under": []}
        }
    
    params = request_data.get("params", {})
    fixture_events = params.get("fixture_events", [])
    translations = params.get("translations", {})
    
    if not isinstance(fixture_events, list):
        return {
            "status": True,
            "data": {"markets_3way": [], "markets_over_under": []}
        }
    
    # Extract all markets
    all_markets = []
    
    for event in fixture_events:
        # Get event name from top level
        event_name = event.get('name', '')
        
        market_data = event.get('market_data', {})
        items = market_data.get('items', [])
        
        for item in items:
            event_id = str(item.get('id', {}).get('entityId', ''))
            
            # Use event name from top level, fallback to constructing from competitors
            if not event_name:
                home = item.get('homeCompetitor', {}).get('name', '')
                away = item.get('awayCompetitor', {}).get('name', '')
                event_title = f"{home} vs {away}" if home and away else 'Event'
            else:
                event_title = event_name
            
            for market in item.get('markets', []):
                market_id = market.get('id')
                market_type_original = market.get('marketType', '')  # Keep original
                market_name_obj = market.get('name', {})
                market_name = market_name_obj.get('text', '') if isinstance(market_name_obj, dict) else str(market_name_obj)
                
                options = []
                for option in market.get('options', []):
                    name_obj = option.get('name', {})
                    option_name = name_obj.get('text', '') if isinstance(name_obj, dict) else str(name_obj)
                    price_obj = option.get('price', {})
                    odds = price_obj.get('odds', 0) if isinstance(price_obj, dict) else 0
                    
                    options.append({
                        'id': option.get('id'),
                        'name': option_name,
                        'odds': odds
                    })
                
                if options:
                    all_markets.append({
                        'event_id': event_id,
                        'event_title': event_title,
                        'market_id': market_id,
                        'market_type': market_type_original,
                        'market_type_original': market_type_original,  # Keep for filtering
                        'market_name': market_name,
                        'options': options
                    })
    
    # Separate by type BEFORE translating
    # 3way: only main "Match Result", exclude "Result after X minutes"
    markets_3way = [
        m for m in all_markets 
        if m.get('market_type_original') == '3way' 
        and 'after' not in m.get('market_name', '').lower()
        and ('match result' in m.get('market_name', '').lower() or '2up' in m.get('market_name', '').lower())
    ][:1]
    
    markets_over_under = [
        m for m in all_markets 
        if m.get('market_type_original', '').lower() in ['over/under', 'total']
    ]
    
    # NOW translate market types
    if translations and isinstance(translations, dict):
        market_types = translations.get('market_types', {})
        for market in markets_3way + markets_over_under:
            mt = market.get('market_type_original', '').lower()
            if mt in market_types:
                market['market_type'] = market_types[mt]
            # Remove the helper field
            market.pop('market_type_original', None)
    
    return {
        "status": True,
        "data": {
            "markets_3way": markets_3way,
            "markets_over_under": markets_over_under
        }
    }

def enrich_matched_events(request_data):
    """
    Enriches matched Kalshi events with fixture information.
    
    Takes matches from fuzzy matching and combines market data with event codes,
    confidence scores, and fixture metadata.
    """
    print("LOG: Starting enrich_matched_events")
    
    params = request_data.get("params", {})
    matches = params.get("matches", [])
    
    if not matches:
        print("LOG: No matches provided")
        return {
            "status": True,
            "data": {
                "enriched_events": []
            }
        }
    
    print(f"LOG: Enriching {len(matches)} matched events")
    
    enriched_events = []
    
    for match in matches:
        market = match.get('market', {})
        event = match.get('event', {})
        event_code = match.get('event_code')
        confidence = match.get('confidence', 0.0)
        
        # Get event value and metadata
        event_value = event.get('value') or {}
        event_metadata = event.get('metadata') or {}
        
        # Get market metadata
        market_metadata = market.get('metadata') or {}
        
        # Build enriched event
        enriched_event = {
            **market,
            'eventCode': event_code,
            'match_confidence': confidence,
            'matched_fixture': event_value.get('title', ''),
            'metadata': {
                **market_metadata,
                'eventCode': event_code,
                'fixture_id': event_metadata.get('fixture_id')
            }
        }
        
        enriched_events.append(enriched_event)
        
        print(f"LOG: Enriched event {market.get('id', 'unknown')} with fixture_id {event_metadata.get('fixture_id')}")
    
    print(f"LOG: Enrichment complete - {len(enriched_events)} events enriched")
    
    return {
        "status": True,
        "data": {
            "enriched_events": enriched_events
        }
    }


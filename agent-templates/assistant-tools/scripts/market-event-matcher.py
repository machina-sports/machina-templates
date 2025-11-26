def match_markets_to_events(request_data):
    """
    Simplified matcher with verbose logging and accent normalization.
    """
    import difflib
    import unicodedata
    from datetime import datetime

    def normalize(text):
        if not text: return ""
        # Remove accents and lowercase
        return unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('utf-8').lower().strip()
    
    def is_outright_market(market):
        """Check if this is an outright/season market rather than a match market"""
        m_val = market.get("value", {})
        m_title = normalize(m_val.get("title", "") or market.get("title", ""))
        
        # Check for outright keywords
        outright_keywords = ['outright', 'winner', 'champion', 'top scorer', 'relegation', 'vencedor']
        if any(keyword in m_title for keyword in outright_keywords):
            return True
        
        # Check if there are participants (matches have teams, outrights don't always)
        participants = m_val.get('participants', [])
        if len(participants) < 2:
            return True
            
        return False

    print("LOG: Starting match_markets_to_events (v3 - normalized + outright filter)")
    
    params = request_data.get("params", {})
    markets = params.get("markets", [])
    events = params.get("events", [])
    
    # Filter out outright markets
    match_markets = [m for m in markets if not is_outright_market(m)]
    outright_count = len(markets) - len(match_markets)
    
    if outright_count > 0:
        print(f"LOG: Filtered out {outright_count} outright/season markets")
    
    print(f"LOG: Processing {len(match_markets)} match markets against {len(events)} events")

    matches = []

    for market in match_markets:
        m_val = market.get("value", {})
        m_title = m_val.get("title", "") or market.get("title", "")
        m_comp = m_val.get("competition", "")
        m_search = normalize(f"{m_title} {m_comp}")
        
        # Date parsing (Market)
        m_date_str = m_val.get("startDate") or m_val.get("startDateUtc", "")
        m_date = None
        if m_date_str:
            try:
                clean = m_date_str.replace('ZT', 'T').replace('Z', '+00:00')
                m_date = datetime.fromisoformat(clean)
            except Exception as e:
                print(f"LOG: Market date parse error: {e}")

        print(f"\nLOG: === Checking Market: '{m_title}' (Date: {m_date}) ===")

        best_event = None
        best_conf = 0.0

        # Extract Market Teams (Normalized)
        m_teams = [normalize(t.get('name', '')) for t in m_val.get('participants', []) if isinstance(t, dict)]

        for event in events:
            e_val = event.get("value", {})
            e_title = e_val.get("title", "") or event.get("title", "")
            e_search = normalize(e_title)
            
            # Date parsing (Event)
            e_date_str = e_val.get("schema:startDate", "") or e_val.get("startDate", "")
            e_date = None
            if e_date_str:
                try:
                    clean = e_date_str.replace('ZT', 'T').replace('Z', '+00:00')
                    e_date = datetime.fromisoformat(clean)
                except:
                    pass

            # 1. Name Score (Normalized)
            name_score = difflib.SequenceMatcher(None, m_search, e_search).ratio()
            
            # 2. Date Score
            date_score = 0.0
            if m_date and e_date:
                dt = m_date - e_date
                hours_diff = abs(dt.total_seconds()) / 3600
                if hours_diff < 24: # 24h tolerance
                    date_score = 1.0
            elif not m_date and not e_date:
                date_score = 0.5

            # 3. Participant/Team Check (Normalized)
            e_teams_raw = e_val.get('sport:competitors', []) or e_val.get('sport:competitor', []) or e_val.get('competitors', [])
            e_teams = []
            if isinstance(e_teams_raw, list):
                for t in e_teams_raw:
                    if isinstance(t, dict):
                        e_teams.append(normalize(t.get('name', '')))
                    elif isinstance(t, str):
                        e_teams.append(normalize(t))

            team_score = 0.0
            if m_teams and e_teams:
                matches_found = 0
                for mt in m_teams:
                    for et in e_teams:
                        if mt in et or et in mt:
                            matches_found += 1
                            break
                team_score = matches_found / max(len(m_teams), 1)

            # Total Confidence
            if team_score > 0:
                conf = (team_score * 0.5) + (name_score * 0.3) + (date_score * 0.2)
            else:
                conf = (name_score * 0.7) + (date_score * 0.3)

            if conf > 0.55: # Log close calls
                print(f"LOG:   vs Event '{e_title}' | Score: {conf:.2f} (Name: {name_score:.2f}, Team: {team_score:.2f}, Date: {date_score})")

            if conf > best_conf:
                best_conf = conf
                best_event = event

        if best_event and best_conf > 0.6:
            print(f"LOG:   >>> MATCHED with {best_conf:.2f}")
            matches.append({
                "market": market,
                "event": best_event,
                "confidence": best_conf,
                "event_code": best_event.get("metadata", {}).get("event_code")
            })
        else:
            print("LOG:   >>> NO MATCH found")

    return {
        "status": True,
        "data": {
            "matches": matches,
            "match_count": len(matches)
        }
    }


def prepare_bulk_update(request_data):
    """
    Prepare matched markets for bulk update with event_code.
    """
    from datetime import datetime
    
    print("LOG: Starting prepare_bulk_update")
    
    params = request_data.get("params", {})
    matches = params.get("matches", [])
    
    prepared_markets = []
    
    for match in matches:
        market = match.get("market", {})
        market_id = market.get("_id")
        market_value = market.get("value", {}) or {}
        market_metadata = market.get("metadata", {}) or {}
        event_code = match.get("event_code", "")
        confidence = match.get("confidence", 0.0)
        
        if not market_id:
            print(f"LOG: Skipping market without _id")
            continue
        
        # Use the market code from metadata as unique identifier
        market_code = market_metadata.get("market_code") or market_value.get("id")
        
        if not market_code:
            print(f"LOG: Skipping market {market_id} without market_code or value.id")
            continue
        
        # Prepare document with updated fields
        # Keep original value structure and add new fields
        updated_market = {
            **market_value,
            "id": market_code,  # Use business ID, not MongoDB _id
            "event_code": event_code,
            "match_confidence": confidence,
            "matched_at": datetime.utcnow().isoformat()
        }
        
        prepared_markets.append(updated_market)
        print(f"LOG: Prepared market {market_code} (_id: {market_id}) with event_code: {event_code}")
    
    print(f"LOG: Prepared {len(prepared_markets)} markets for bulk update")
    
    return {
        "status": True,
        "data": {
            "prepared_markets": prepared_markets
        }
    }

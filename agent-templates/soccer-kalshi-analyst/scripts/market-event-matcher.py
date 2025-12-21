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
    
    def looks_like_match_title(text):
        t = normalize(text)
        # Simple heuristics to catch matchup strings even when participants are missing
        return any(pat in t for pat in [" vs ", " v ", " x "]) or (" - " in t and " vs " in t.replace("-", " - "))

    def strip_code_prefix(text):
        """Remove leading code/ticker before the first ' - ' to avoid polluting team names."""
        if not text or " - " not in text:
            return text
        parts = text.split(" - ", 1)
        return parts[1].strip() if len(parts) == 2 else text

    def extract_teams_from_title(text):
        """
        Best-effort team extraction when participants are missing.
        Splits on common separators: vs, v, x, '-', '–'.
        """
        if not text:
            return []
        t = normalize(strip_code_prefix(text))
        # Replace separators with a common token
        for sep in [" vs ", " v ", " x ", " - ", " – "]:
            t = t.replace(sep, "|")
        parts = [p.strip() for p in t.split("|") if p.strip()]
        # Keep only up to 3 to avoid noise
        return parts[:3]

    def is_outright_market(market):
        """Check if this is an outright/season market rather than a match market"""
        m_val = market.get("value", {})
        # Prefer originalTitle/subtitle for matchup text; fallback to title
        m_title = m_val.get("title", "") or market.get("title", "")
        m_title_primary = m_val.get("originalTitle", "") or m_val.get("subtitle", "") or m_title
        m_title_clean = strip_code_prefix(m_title_primary or m_title)
        m_title_norm = normalize(m_title)
        m_alt_title = m_val.get("originalTitle", "") or m_val.get("subtitle", "")
        m_alt_title_norm = normalize(m_alt_title)
        
        # Check for outright keywords
        outright_keywords = ['outright', 'winner', 'champion', 'top scorer', 'relegation', 'vencedor']
        if any(keyword in m_title_norm for keyword in outright_keywords):
            return True
        
        # If participants are missing, but the title looks like a matchup, treat as match market
        participants = m_val.get('participants', [])
        if len(participants) < 2:
            if looks_like_match_title(m_title) or looks_like_match_title(m_alt_title):
                return False
            return True
            
        return False

    print("LOG: Starting match_markets_to_events (v3 - normalized + outright filter)")
    
    params = request_data.get("params", {})
    markets = params.get("markets", [])
    events = params.get("events", [])
    
    print(f"LOG: Total markets received: {len(markets)}")
    print(f"LOG: Total events received: {len(events)}")
    
    # Filter out outright markets
    match_markets = [m for m in markets if not is_outright_market(m)]
    outright_count = len(markets) - len(match_markets)
    
    if outright_count > 0:
        print(f"LOG: Filtered out {outright_count} outright/season markets")
    
    print(f"LOG: Processing {len(match_markets)} match markets against {len(events)} events")
    
    # Check if any event carries a date (some Kalshi events have none)
    def parse_date_safe(date_str):
        if not date_str:
            return None
        try:
            clean = date_str.replace('ZT', 'T').replace('Z', '+00:00')
            return datetime.fromisoformat(clean)
        except Exception:
            return None

    event_dates_available = False
    for ev in events:
        ev_val = ev.get("value", {}) or {}
        ev_date = parse_date_safe(ev_val.get("schema:startDate", "") or ev_val.get("startDate", ""))
        if ev_date:
            event_dates_available = True
            break

    # Debug: print all events received
    for idx, event in enumerate(events[:5]):  # Show first 5
        e_val = event.get("value", {})
        e_title = e_val.get("title", "") or event.get("title", "")
        e_date = e_val.get("schema:startDate", "") or e_val.get("startDate", "")
        print(f"LOG: Event {idx}: '{e_title}' | Date: {e_date or 'N/A'}")

    if not event_dates_available:
        print("LOG: No event dates detected — date score will be ignored.")

    matches = []

    for m_idx, market in enumerate(match_markets):
        m_val = market.get("value", {})
        m_title = m_val.get("title", "") or market.get("title", "")
        m_title_primary = m_val.get("originalTitle", "") or m_val.get("subtitle", "") or m_title
        m_title_clean = strip_code_prefix(m_title_primary or m_title)
        m_comp = m_val.get("competition", "")
        m_search = normalize(f"{m_title_clean} {m_comp}")
        
        # Date parsing (Market)
        m_date_str = m_val.get("startDate") or m_val.get("startDateUtc", "")
        m_date = parse_date_safe(m_date_str)
        if m_date_str and m_date is None:
            print(f"LOG: Market date parse error for '{m_title}': {m_date_str}")

        print(f"\nLOG: === Market {m_idx}: '{m_title}' (Date: {m_date}, Comp: {m_comp}) ===")
        
        # Extract Market Teams (Normalized)
        m_teams_raw = m_val.get('participants', [])
        m_teams = [normalize(t.get('name', '')) for t in m_teams_raw if isinstance(t, dict)]
        if not m_teams:
            # Try to derive from title/originalTitle/subtitle for Kalshi formats
            derived = extract_teams_from_title(m_title_primary) or extract_teams_from_title(m_val.get("originalTitle", "")) or extract_teams_from_title(m_val.get("subtitle", "")) or extract_teams_from_title(m_title)
            m_teams = derived
        print(f"LOG: Market Teams: {m_teams}")

        best_event = None
        best_conf = 0.0

        for e_idx, event in enumerate(events):
            e_val = event.get("value", {})
            e_title = e_val.get("title", "") or event.get("title", "")
            e_search = normalize(e_title)
            
            # Date parsing (Event)
            e_date_str = e_val.get("schema:startDate", "") or e_val.get("startDate", "")
            e_date = parse_date_safe(e_date_str)

            # 1. Name Score (Normalized)
            name_score = difflib.SequenceMatcher(None, m_search, e_search).ratio()
            
            # 2. Date Score
            date_score = 0.0
            if event_dates_available:
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
            if event_dates_available:
                if team_score > 0:
                    conf = (team_score * 0.5) + (name_score * 0.3) + (date_score * 0.2)
                else:
                    conf = (name_score * 0.7) + (date_score * 0.3)
            else:
                if team_score > 0:
                    conf = (team_score * 0.6) + (name_score * 0.4)
                else:
                    conf = name_score

            # Log ALL comparisons with details (for debugging)
            print(f"LOG:   Event {e_idx}: '{e_title}' | Conf: {conf:.2f} (Name: {name_score:.2f}, Team: {team_score:.2f}, Date: {date_score if event_dates_available else 'ignored'})")
            if e_teams:
                print(f"LOG:     Event Teams: {e_teams}")
            
            if conf > 0.55: # Log close calls
                print(f"LOG:     >>> Close call! Score above 0.55")

            if conf > best_conf:
                best_conf = conf
                best_event = event
                print(f"LOG:     >>> New best match! (prev: {best_conf:.2f})")

        if best_event and best_conf > 0.5:
            best_event_title = best_event.get("value", {}).get("title", "") or best_event.get("title", "")
            print(f"LOG:   >>> ✓ MATCHED with confidence {best_conf:.2f}")
            print(f"LOG:       Matched event: '{best_event_title}'")
            matches.append({
                "market": market,
                "event": best_event,
                "confidence": best_conf,
                "event_code": best_event.get("metadata", {}).get("event_code")
            })
        else:
            print(f"LOG:   >>> ✗ NO MATCH found (best_conf: {best_conf:.2f}, threshold: 0.5, has_event: {best_event is not None})")

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


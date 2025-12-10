def invoke_filter_interesting_odds(request_data):
    """
    Filter odds between 1.50-3.00 for: Total Goals, Team Total Goals, First To Score.
    Extract additional odds: Both Teams Score (lowest odd), First Half and Match (lowest odd), Corners (1.60-2.00).
    Translate market names to Brazilian Portuguese.
    
    Args:
        request_data: Dictionary with params containing all_markets_mapped
        
    Returns:
        Dictionary with filtered odds and formatted text, plus additional special odds
    """
    import re
    
    params = request_data.get("params", {})
    all_markets = params.get("all_markets_mapped", [])
    
    # WHITELIST: Total Goals, Team Goals, First Scorer
    allowed_market_types = {
        "Over/Under",              # Total de Gols (Acima/Abaixo)
        "TeamTotalGoals",          # Total de Gols por Time
        "Team Total Goals",        # Variação do nome
        "FirstToScore",            # Quem Marca Primeiro
        "First To Score",          # Variação do nome
    }
    
    # Market name translations to Brazilian Portuguese
    market_translations = {
        "Over/Under": "Total de Gols",
        "TeamTotalGoals": "Total de Gols do Time",
        "Team Total Goals": "Total de Gols do Time",
        "FirstToScore": "Quem Marca Primeiro",
        "First To Score": "Quem Marca Primeiro",
        "3way": "Resultado Final",
        "3Way": "Resultado Final",
        "both_teams_score": "Ambas Marcam",
        "BothTeamsScore": "Ambas Marcam",
        "correct_score": "Placar Exato",
        "CorrectScore": "Placar Exato",
        "Scorer": "Goleador",
        "ExactGoals": "Gols Exatos"
    }
    
    # Team suffixes to remove for cleaner display
    team_suffixes = [
        ' Calcio', ' CFC', ' FC', ' SC', ' EC', ' AC', ' CF', ' SV',
        ' United', ' City', ' Town', ' Wanderers', ' Rovers',
        ' FBPA', ' MG', ' RJ', ' SP', ' RS', ' BA', ' PE', ' CE', ' GO', ' PR',
        ' de Futebol', ' Futebol Clube', ' Esporte Clube', ' Sport Club',
        ' Football Club', ' Association', ' Fußball-Club', ' Fußballclub'
    ]
    
    def normalize_runner_name(name):
        """Remove team suffixes and clean up runner names"""
        cleaned = name
        for suffix in team_suffixes:
            cleaned = cleaned.replace(suffix, '')
        return cleaned.strip()
    
    interesting_odds = []
    debug_samples = []
    all_market_types = set()  # DEBUG: collect all market types
    
    for runner in all_markets:
        if not isinstance(runner, dict):
            continue
            
        price = runner.get("price", 0)
        market_type = runner.get("marketType", "")
        runner_name = runner.get("name", "")
        
        # DEBUG: Collect all market types
        if market_type:
            all_market_types.add(market_type)
        
        # Filter range 1.50 - 3.00 (inclusive) - focusing on Total Goals
        if 1.50 <= price <= 3.00:
            
            # Skip if no valid data
            if not market_type or not runner_name:
                continue
            
            # WHITELIST: Only accept popular markets
            if market_type not in allowed_market_types:
                continue
            
            # DEBUG: Collect sample data to understand structure
            if len(debug_samples) < 10:
                debug_samples.append({
                    "marketType": market_type,
                    "name": runner_name,
                    "price": price,
                    "title": runner.get("title", ""),
                })
                print(f"🔍 DEBUG: {runner_name} ({price}) | title: {runner.get('title', 'N/A')[:80]}")
            
            # FILTER 1: Check title for valid markets
            title = runner.get("title", "").lower()
            
            # Skip half-time markets
            skip_keywords = ['1º tempo', '2º tempo', 'first half', 'second half', '1st half', '2nd half', 
                            'intervalo', 'half time']
            if any(keyword in title for keyword in skip_keywords):
                print(f"⏩ SKIP (half-time): {title[:80]}")
                continue
            
            # Skip corners, cards, and other non-goal markets
            if 'corner' in title or 'card' in title:
                print(f"⏩ SKIP (corners/cards): {title[:80]}")
                continue
            
            # FILTER 2: Apply different rules per market type
            if market_type == "Over/Under":
                # For Total Goals: Only accept FULL MATCH (not team-specific)
                if ' - total goals' in title and '| total goals' not in title:
                    print(f"⏩ SKIP (team-specific goals): {title[:80]}")
                    continue
                
                # Extract and validate goal lines (ONLY 1.5, 2.5, 3.5)
                goal_line_match = re.search(r'(Over|Under)\s+(\d+[,.]?\d*)', runner_name)
                if goal_line_match:
                    line_value = float(goal_line_match.group(2).replace(',', '.'))
                    if line_value not in [1.5, 2.5, 3.5]:
                        continue
                else:
                    continue
            
            elif market_type in ["TeamTotalGoals", "Team Total Goals"]:
                # For Team Total Goals: Accept team-specific goal lines (0.5, 1.5, 2.5)
                goal_line_match = re.search(r'(Over|Under)\s+(\d+[,.]?\d*)', runner_name)
                if goal_line_match:
                    line_value = float(goal_line_match.group(2).replace(',', '.'))
                    if line_value not in [0.5, 1.5, 2.5]:
                        continue
                else:
                    continue
            
            elif market_type in ["FirstToScore", "First To Score"]:
                # For First To Score: No additional validation needed
                pass
            
            # Translate market type to Portuguese
            market_pt = market_translations.get(market_type, market_type)
            
            # Normalize runner name (remove team suffixes)
            runner_normalized = normalize_runner_name(runner_name)
            
            # Translate Over/Under to Portuguese
            runner_normalized = runner_normalized.replace("Over", "Mais de")
            runner_normalized = runner_normalized.replace("Under", "Menos de")
            
            # Format: "Market: Runner (odds)"
            formatted = f"{market_pt}: {runner_normalized} ({price:.2f})"
            
            interesting_odds.append({
                "market": market_pt,
                "market_type": market_type,
                "runner": runner_normalized,
                "price": price,
                "formatted": formatted
            })
    
    # Diversify selection: group by price ranges and pick from each
    if interesting_odds:
        # Group by price ranges: 1.50-1.85, 1.86-2.20, 2.21-2.60, 2.61-3.00
        ranges = {
            "low": [o for o in interesting_odds if 1.50 <= o["price"] <= 1.85],
            "mid_low": [o for o in interesting_odds if 1.86 <= o["price"] <= 2.20],
            "mid_high": [o for o in interesting_odds if 2.21 <= o["price"] <= 2.60],
            "high": [o for o in interesting_odds if 2.61 <= o["price"] <= 3.00]
        }
        
        # Select diversified odds (max 2 per range)
        selected = []
        for range_key in ["low", "mid_low", "mid_high", "high"]:
            range_odds = ranges[range_key]
            if range_odds:
                # Sort by price for better distribution
                sorted_odds = sorted(range_odds, key=lambda x: x["price"])
                selected.extend(sorted_odds[:2])  # Max 2 per range
        
        # Limit to 10 total (Total Goals + Team Goals + First Scorer)
        interesting_odds = selected[:10]
    
    # Create formatted text for article
    if interesting_odds:
        odds_list = ", ".join([o["formatted"] for o in interesting_odds])
        odds_text = f"Odds interessantes: {odds_list}"
    else:
        odds_text = ""
    
    # DEBUG: Print all market types found
    print(f"\n🔍 ALL MARKET TYPES FOUND: {sorted(all_market_types)}\n")
    
    # EXTRACT SPECIAL ODDS (BTTS, HT/FT, Corners, Player Both Halves)
    
    # Extract BTTS (Both Teams To Score) - return object with lowest odds
    # Filter: marketType=BTTS, happening=Goal, period=RegularTime
    btts_runners = [
        r for r in all_markets 
        if r.get("marketType") == "BTTS" 
        and r.get("happening", "") == "Goal"
        and r.get("period", "") == "RegularTime"
    ]
    btts_obj = min(btts_runners, key=lambda x: x.get('price', float('inf'))) if btts_runners else None
    print(f"\n📊 BTTS: Found {len(btts_runners)} options, selected lowest odds")
    
    # Extract First Half and Match (HTandFTV2) - return entire object with lowest price
    htft_runners = [r for r in all_markets if r.get("marketType") == "HTandFTV2"]
    htft_obj = min(htft_runners, key=lambda x: x.get('price', float('inf'))) if htft_runners else None
    
    # Extract Total Corners - option in range 1.60-2.00
    # Filter: marketType=Over/Under, happening=Corner, period=RegularTime, price 1.60-2.00
    corners_runners = [
        r for r in all_markets 
        if r.get("marketType") == "Over/Under" 
        and r.get("happening", "") == "Corner"
        and r.get("period", "") == "RegularTime"
        and 1.60 <= float(r.get('price', 0)) <= 2.00
    ]
    corners_obj = corners_runners[0] if corners_runners else None
    print(f"\n🏀 Total Corners: Found {len(corners_runners)} options in range 1.60-2.00")
    
    # Extract Anytime Goalscorer - player with lowest odds
    # Filter by: marketType=Scorer, title contains "Anytime Goalscorer"
    anytime_goalscorers_all = [
        r for r in all_markets 
        if r.get("marketType") == "Scorer" 
        and "Anytime Goalscorer" in r.get("title", "")
    ]
    anytime_goalscorer_lowest = min(anytime_goalscorers_all, key=lambda x: x.get('price', float('inf'))) if anytime_goalscorers_all else None
    print(f"\n⚽ Anytime Goalscorer: Found {len(anytime_goalscorers_all)} options, selected player with lowest odds")
    
    special_odds = {
        'btts': btts_obj,
        'ht_ft': htft_obj,
        'corners': corners_obj,
        'anytime_goalscorer': anytime_goalscorer_lowest
    }
    
    # Create formatted text for special odds
    special_odds_text_parts = []
    
    # Market type translations for special odds
    special_translations = {
        "BTTS": "Ambos marcam",
        "HTandFTV2": "1º tempo e resultado final",
        "Over/Under": "Total de cantos"
    }
    
    if btts_obj:
        btts_name = btts_obj.get('name', '')
        btts_price = btts_obj.get('price', 0)
        special_odds_text_parts.append(f"Ambos marcam ({btts_price:.2f})")
    
    if htft_obj:
        htft_name = htft_obj.get('name', '')
        htft_price = htft_obj.get('price', 0)
        special_odds_text_parts.append(f"1º tempo e resultado final: {htft_name} ({htft_price:.2f})")
    
    if corners_obj:
        corners_name = corners_obj.get('name', '')
        corners_price = corners_obj.get('price', 0)
        # Translate Over/Under to Portuguese
        corners_name = corners_name.replace("Over", "Acima")
        corners_name = corners_name.replace("Under", "Abaixo")
        special_odds_text_parts.append(f"Total de cantos: {corners_name} ({corners_price:.2f})")
    
    if anytime_goalscorer_lowest:
        player_name = anytime_goalscorer_lowest.get('name', '')
        scorer_price = anytime_goalscorer_lowest.get('price', 0)
        special_odds_text_parts.append(f"Marcador a qualquer momento: {player_name} ({scorer_price:.2f})")
    
    special_odds_text = " • ".join(special_odds_text_parts) if special_odds_text_parts else ""
    
    # DEBUG: Print extraction results
    print(f"\n🎯 Special Odds Extracted:")
    print(f"   BTTS: {'Found' if btts_obj else 'Not found'}")
    print(f"   HT/FT: {'Found' if htft_obj else 'Not found'}")
    print(f"   Corners: {'Found' if corners_obj else 'Not found'}")
    print(f"   Anytime Goalscorer (lowest odds): {'Found' if anytime_goalscorer_lowest else 'Not found'}")
    print(f"\n📝 Special Odds Text:\n   {special_odds_text}")
    
    return {
        "status": True,
        "message": f"Found {len(interesting_odds)} interesting odds (Total Goals, Team Goals, First Scorer) in range 1.50-3.00",
        "data": {
            "interesting_odds": interesting_odds,
            "interesting_odds_text": odds_text,
            "has_interesting_odds": len(interesting_odds) > 0,
            "special_odds": special_odds,
            "special_odds_text": special_odds_text,
            "debug_all_market_types": sorted(all_market_types)  # DEBUG
        }
    }


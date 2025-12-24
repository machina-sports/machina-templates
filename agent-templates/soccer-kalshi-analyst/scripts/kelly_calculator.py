def calculate_kelly_position(request_data):
    """
    Calculate Kelly Criterion stake sizing and Expected Value for prediction market trading.
    Returns in the standard pyscript pattern: {status, data, message}
    
    The Kelly Criterion determines optimal bet sizing to maximize long-term growth:
        f* = (bp - q) / b
    where:
        b = decimal odds - 1 (net odds)
        p = probability of winning
        q = probability of losing (1 - p)
    
    Parameters:
        our_prob: Our model's probability for the outcome (0-1)
        market_price: Kalshi market price in cents (1-99)
        confidence: Model confidence (0-1)
        bankroll: Optional bankroll size for stake calculation
        side: 'yes' or 'no' position
    """
    try:
        # Import inside function to ensure availability in pyscript execution
        import json
        import math
        
        # Parse request_data
        if isinstance(request_data, str):
            try:
                request_data = json.loads(request_data)
            except:
                pass
        
        if not isinstance(request_data, dict):
            request_data = {}
        
        # Get params from request_data (standard pyscript pattern)
        params = request_data.get('params', request_data)
        if not isinstance(params, dict):
            params = {}
        
        # Extract inputs with validation
        our_prob = params.get('our_prob')
        market_price = params.get('market_price')
        
        if our_prob is None or market_price is None:
            return {
                "status": False,
                "data": {"error": "Missing required parameters: our_prob and market_price"},
                "message": "Missing required parameters"
            }
        
        # Convert and validate
        our_prob = float(our_prob)
        market_price = float(market_price)
        confidence = float(params.get('confidence', 0.5))
        bankroll = float(params.get('bankroll', 1000))
        fractional_kelly = float(params.get('fractional_kelly', 0.25))
        side = params.get('side', 'yes')
        max_stake_percent = float(params.get('max_stake_percent', 10.0))
        min_edge_threshold = float(params.get('min_edge_threshold', 0.03))
        min_ev_threshold = float(params.get('min_ev_threshold', 3.0))
        
        # Clamp values to valid ranges
        our_prob = max(0.01, min(0.99, our_prob))
        market_price = max(1, min(99, market_price))
        confidence = max(0.1, min(1.0, confidence))
        fractional_kelly = max(0.1, min(1.0, fractional_kelly))
        
        # Calculate implied probability from market price
        implied_prob = market_price / 100.0
        
        # Determine effective probability based on side
        if side == 'yes':
            p = our_prob  # Our probability for YES
            market_implied = implied_prob
            # Net odds for YES: if market is 40 cents, you pay 40 to win 60 = 1.5x return
            net_odds = (100 - market_price) / market_price
        else:  # no
            p = 1 - our_prob  # Our probability for NO (complement)
            market_implied = 1 - implied_prob
            # Net odds for NO: if market is 40 cents YES, NO costs 60 to win 40 = 0.67x return
            net_odds = market_price / (100 - market_price)
        
        # Calculate edge (our probability minus implied)
        edge = p - market_implied
        edge_percent = edge * 100
        
        # Calculate Expected Value per dollar wagered
        # EV = (probability of winning × net profit) - (probability of losing × stake)
        q = 1 - p
        ev = (p * net_odds) - q
        ev_cents = ev * 100  # Convert to cents per dollar
        
        # Calculate Kelly Criterion: f* = (bp - q) / b
        # where b = net_odds, p = win probability, q = lose probability
        if net_odds > 0:
            kelly_full = (net_odds * p - q) / net_odds
        else:
            kelly_full = 0
        
        # Apply confidence adjustment and fractional Kelly
        confidence_adjusted_kelly = kelly_full * confidence
        final_kelly = max(0, confidence_adjusted_kelly * fractional_kelly)
        
        # Calculate recommended stake
        recommended_stake_percent = min(final_kelly * 100, max_stake_percent)
        recommended_stake = bankroll * (recommended_stake_percent / 100)
        
        # Determine if this is a tradeable opportunity
        should_trade = (
            edge > min_edge_threshold and 
            ev_cents > min_ev_threshold and 
            final_kelly > 0
        )
        
        # Build result
        result = {
            "position_analysis": {
                "side": side,
                "our_probability": round(p, 4),
                "implied_probability": round(market_implied, 4),
                "edge": round(edge, 4),
                "edge_percent": round(edge_percent, 2),
                "expected_value_cents": round(ev_cents, 2),
                "market_price": market_price,
                "net_odds": round(net_odds, 4)
            },
            "kelly_analysis": {
                "full_kelly_fraction": round(kelly_full, 4),
                "confidence_adjusted_kelly": round(confidence_adjusted_kelly, 4),
                "fractional_kelly_multiplier": fractional_kelly,
                "final_kelly_fraction": round(final_kelly, 4)
            },
            "stake_recommendation": {
                "recommended_stake_percent": round(recommended_stake_percent, 2),
                "recommended_stake_dollars": round(recommended_stake, 2),
                "bankroll_assumed": bankroll,
                "max_stake_cap_percent": max_stake_percent
            },
            "trading_decision": {
                "should_trade": should_trade,
                "minimum_edge_required": min_edge_threshold,
                "minimum_ev_required": min_ev_threshold,
                "edge_sufficient": edge > min_edge_threshold,
                "ev_sufficient": ev_cents > min_ev_threshold
            }
        }
        
        return {
            "status": True,
            "data": result,
            "message": f"Kelly analysis complete: edge={edge_percent:.2f}%, EV={ev_cents:.2f}¢, stake={recommended_stake_percent:.2f}%"
        }
    
    except Exception as e:
        return {
            "status": False,
            "data": {"error": str(e)},
            "message": f"Kelly calculation error: {str(e)}"
        }


def batch_kelly_analysis(request_data):
    """
    Calculate Kelly analysis for multiple markets/outcomes.
    Returns in the standard pyscript pattern: {status, data, message}
    
    Accepts raw market data from Kalshi API and prediction data, then:
    1. Matches markets to probabilities based on team names
    2. Calculates Kelly criterion for each market
    3. Returns ranked results
    
    Parameters:
        raw_markets: List of market objects from Kalshi API
        prediction: Dict with home_win_probability, away_win_probability, draw_probability
        home_team: Home team name
        away_team: Away team name
        confidence: Overall model confidence
        bankroll: Total bankroll
        
    Output:
        Ranked list of markets by expected value
    """
    try:
        # Import inside function to ensure availability in pyscript execution
        import json
        import math
        
        # Helper function for Kelly calculation (defined inside to ensure scope)
        def calc_kelly_single(our_prob, market_price, confidence, bankroll, side='yes'):
            """Calculate Kelly for a single market."""
            # Validate and convert inputs
            our_prob = float(our_prob)
            market_price = float(market_price)
            confidence = float(confidence) if confidence else 0.5
            bankroll = float(bankroll) if bankroll else 1000
            
            # Clamp values
            our_prob = max(0.01, min(0.99, our_prob))
            market_price = max(1, min(99, market_price))
            confidence = max(0.1, min(1.0, confidence))
            
            # Calculate implied probability from market
            implied_prob = market_price / 100.0
            
            # Determine effective probability based on side
            if side == 'yes':
                p = our_prob
                market_implied = implied_prob
                net_odds = (100 - market_price) / market_price if market_price > 0 else 0
            else:  # no
                p = 1 - our_prob
                market_implied = 1 - implied_prob
                net_odds = market_price / (100 - market_price) if market_price < 100 else 0
            
            # Calculate edge
            edge = p - market_implied
            edge_percent = edge * 100
            
            # Calculate Expected Value
            q = 1 - p
            ev = (p * net_odds) - q if net_odds > 0 else -q
            ev_cents = ev * 100
            
            # Calculate Kelly fraction: f* = (bp - q) / b
            if net_odds > 0:
                kelly_full = (net_odds * p - q) / net_odds
            else:
                kelly_full = 0
            
            # Apply fractional Kelly (25%) and confidence adjustment
            fractional_kelly = 0.25
            confidence_adjusted_kelly = kelly_full * confidence
            final_kelly = max(0, confidence_adjusted_kelly * fractional_kelly)
            
            # Calculate stake
            max_stake_percent = 10.0  # Cap at 10%
            recommended_stake_percent = min(final_kelly * 100, max_stake_percent)
            recommended_stake = bankroll * (recommended_stake_percent / 100)
            
            # Determine if tradeable
            min_edge = 0.03  # 3% minimum edge
            min_ev = 3.0  # 3 cents minimum EV
            should_trade = edge > min_edge and ev_cents > min_ev and final_kelly > 0
            
            return {
                'our_prob': round(p, 4),
                'market_implied': round(market_implied, 4),
                'edge_percent': round(edge_percent, 2),
                'ev_cents': round(ev_cents, 2),
                'kelly_full': round(kelly_full, 4),
                'kelly_percent': round(recommended_stake_percent, 2),
                'stake_dollars': round(recommended_stake, 2),
                'should_trade': should_trade,
                'net_odds': round(net_odds, 4)
            }
        
        # Helper to match market subtitle to probability
        def get_prob_for_market(yes_subtitle, home_team, away_team, prediction):
            """Match market subtitle to the correct probability from prediction."""
            subtitle_lower = yes_subtitle.lower() if yes_subtitle else ''
            home_lower = home_team.lower() if home_team else ''
            away_lower = away_team.lower() if away_team else ''
            
            # Check for home team match
            if home_lower and home_lower in subtitle_lower:
                return prediction.get('home_win_probability', 0.33), 'home_win'
            
            # Check for away team match
            if away_lower and away_lower in subtitle_lower:
                return prediction.get('away_win_probability', 0.33), 'away_win'
            
            # Check for draw/tie
            if 'draw' in subtitle_lower or 'tie' in subtitle_lower:
                return prediction.get('draw_probability', 0.33), 'draw'
            
            # Default fallback
            return 0.33, 'unknown'
        
        # Parse request_data
        if isinstance(request_data, str):
            try:
                request_data = json.loads(request_data)
            except:
                pass
        
        if not isinstance(request_data, dict):
            request_data = {}
        
        # Get params from request_data (standard pyscript pattern)
        params = request_data.get('params', request_data)
        if not isinstance(params, dict):
            params = {}
        
        # Extract inputs - support both old format (markets) and new format (raw_markets)
        raw_markets = params.get('raw_markets', params.get('markets', []))
        prediction = params.get('prediction', {})
        home_team = params.get('home_team', '')
        away_team = params.get('away_team', '')
        confidence = params.get('confidence', 0.5)
        bankroll = params.get('bankroll', 1000)
        
        # Ensure raw_markets is a list
        if not isinstance(raw_markets, list):
            raw_markets = []
        
        if not raw_markets:
            return {
                "status": False,
                "data": {"error": "No markets provided", "params_received": list(params.keys())},
                "message": "No markets to analyze"
            }
        
        results = []
        
        for market in raw_markets:
            if not isinstance(market, dict):
                continue
                
            # Extract market data from Kalshi API format
            ticker = market.get('ticker', 'unknown')
            market_title = market.get('title', '')
            yes_subtitle = market.get('yes_sub_title', '')
            market_price = market.get('yes_ask', 50)  # Use ask price
            
            # Match market to probability
            our_prob, outcome_type = get_prob_for_market(yes_subtitle, home_team, away_team, prediction)
            
            # Calculate Kelly using helper function
            analysis = calc_kelly_single(our_prob, market_price, confidence, bankroll, 'yes')
            
            if analysis:
                results.append({
                    'ticker': ticker,
                    'market_title': market_title,
                    'yes_subtitle': yes_subtitle,
                    'outcome_type': outcome_type,
                    'side': 'yes',
                    'our_prob': round(our_prob, 4),
                    'market_price': market_price,
                    'market_implied': analysis['market_implied'],
                    'edge_percent': analysis['edge_percent'],
                    'ev_cents': analysis['ev_cents'],
                    'kelly_full': analysis['kelly_full'],
                    'kelly_percent': analysis['kelly_percent'],
                    'stake_dollars': analysis['stake_dollars'],
                    'should_trade': analysis['should_trade'],
                    'net_odds': analysis['net_odds']
                })
        
        # Sort by expected value (highest first)
        results.sort(key=lambda x: x.get('ev_cents', 0), reverse=True)
        
        # Find best trade
        tradeable = [r for r in results if r.get('should_trade')]
        best_trade = tradeable[0] if tradeable else None
        
        # Build summary statistics
        total_positive_ev = sum(r['ev_cents'] for r in results if r['ev_cents'] > 0)
        avg_edge = sum(r['edge_percent'] for r in results) / len(results) if results else 0
        
        return {
            "status": True,
            "data": {
                "markets_analyzed": len(results),
                "tradeable_count": len(tradeable),
                "best_trade": best_trade,
                "all_markets_ranked": results,
                "summary": {
                    "total_positive_ev_cents": round(total_positive_ev, 2),
                    "average_edge_percent": round(avg_edge, 2),
                    "confidence_used": confidence,
                    "bankroll_assumed": bankroll
                },
                "inputs_received": {
                    "home_team": home_team,
                    "away_team": away_team,
                    "markets_count": len(raw_markets),
                    "prediction_keys": list(prediction.keys()) if prediction else []
                }
            },
            "message": f"Analyzed {len(results)} markets, {len(tradeable)} tradeable"
        }
    
    except Exception as e:
        return {
            "status": False,
            "data": {"error": str(e)},
            "message": f"Batch analysis error: {str(e)}"
        }

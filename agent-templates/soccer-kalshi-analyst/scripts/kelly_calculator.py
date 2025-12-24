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
    
    Parameters:
        markets: List of market objects with our_prob, market_price, side, ticker
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
                net_odds = (100 - market_price) / market_price
            else:  # no
                p = 1 - our_prob
                market_implied = 1 - implied_prob
                net_odds = market_price / (100 - market_price)
            
            # Calculate edge
            edge = p - market_implied
            edge_percent = edge * 100
            
            # Calculate Expected Value
            q = 1 - p
            ev = (p * net_odds) - q
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
        
        markets = params.get('markets', [])
        confidence = params.get('confidence', 0.5)
        bankroll = params.get('bankroll', 1000)
        
        if not markets:
            return {
                "status": False,
                "data": {"error": "No markets provided"},
                "message": "No markets to analyze"
            }
        
        results = []
        
        for market in markets:
            ticker = market.get('ticker', 'unknown')
            our_prob = market.get('our_prob')
            market_price = market.get('market_price')
            side = market.get('side', 'yes')
            market_type = market.get('market_type', '')
            yes_subtitle = market.get('yes_subtitle', '')
            
            if our_prob is None or market_price is None:
                continue
            
            # Calculate Kelly using helper function
            analysis = calc_kelly_single(our_prob, market_price, confidence, bankroll, side)
            
            if analysis:
                results.append({
                    'ticker': ticker,
                    'market_type': market_type,
                    'yes_subtitle': yes_subtitle,
                    'side': side,
                    'our_prob': analysis['our_prob'],
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

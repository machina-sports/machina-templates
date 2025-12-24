import json


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
    
    Input:
        our_prob: Our model's probability for the outcome (0-1)
        market_price: Kalshi market price in cents (1-99)
        confidence: Model confidence (0-1)
        bankroll: Optional bankroll size for stake calculation
        fractional_kelly: Kelly fraction to use (default 0.25 for quarter Kelly)
    
    Output:
        expected_value: EV in cents per dollar wagered
        kelly_fraction: Optimal bet fraction (before applying fractional Kelly)
        adjusted_kelly: Kelly fraction after confidence adjustment
        recommended_stake_percent: Final recommended stake as % of bankroll
        edge: Our probability minus implied probability
    """
    try:
        # Parse request_data
        if isinstance(request_data, str):
            try:
                request_data = json.loads(request_data)
            except:
                pass
        
        if not isinstance(request_data, dict):
            request_data = {}
        
        params = request_data.get('params', request_data)
        if not isinstance(params, dict):
            params = {}
        
        # Extract inputs
        our_prob = params.get('our_prob')
        market_price = params.get('market_price')
        confidence = params.get('confidence', 0.5)
        bankroll = params.get('bankroll', 1000)  # Default $1000
        fractional_kelly = params.get('fractional_kelly', 0.25)  # Quarter Kelly default
        side = params.get('side', 'yes')  # 'yes' or 'no'
        
        if our_prob is None or market_price is None:
            return {
                "status": False,
                "data": {"error": "Missing our_prob or market_price"},
                "message": "Missing required inputs"
            }
        
        our_prob = float(our_prob)
        market_price = float(market_price)
        confidence = float(confidence)
        bankroll = float(bankroll)
        fractional_kelly = float(fractional_kelly)
        
        # Validate inputs
        if not (0 < our_prob < 1):
            return {
                "status": False,
                "data": {"error": f"our_prob must be between 0 and 1, got {our_prob}"},
                "message": "Invalid probability"
            }
        
        if not (1 <= market_price <= 99):
            return {
                "status": False,
                "data": {"error": f"market_price must be between 1 and 99 cents, got {market_price}"},
                "message": "Invalid market price"
            }
        
        # Convert market price to implied probability
        # On Kalshi: YES price of 60 means $0.60 to win $1.00 if YES
        # Implied probability = price / 100
        if side == 'yes':
            implied_prob = market_price / 100
            # Decimal odds for YES: payout / cost = 100 / market_price
            # Net odds (b) = (100 / market_price) - 1 = (100 - market_price) / market_price
            b = (100 - market_price) / market_price
            p = our_prob  # Our probability of YES winning
        else:
            implied_prob = (100 - market_price) / 100
            # For NO: cost = 100 - market_price, payout = 100
            # Net odds (b) = market_price / (100 - market_price)
            b = market_price / (100 - market_price)
            p = 1 - our_prob  # Our probability of NO winning (YES losing)
        
        q = 1 - p  # Probability of losing
        
        # Calculate edge
        edge = p - implied_prob
        edge_percent = edge * 100
        
        # Calculate Expected Value
        # EV = (p × net_win) - (q × stake) = p × b - q
        # Per $1 wagered
        ev = (p * b) - q
        ev_cents = ev * 100  # EV in cents per dollar
        
        # Calculate Kelly fraction
        # f* = (bp - q) / b = (b × p - q) / b
        if b > 0:
            kelly_full = (b * p - q) / b
        else:
            kelly_full = 0
        
        # Cap Kelly at 0 (no bet) if negative
        kelly_full = max(0, kelly_full)
        
        # Apply confidence adjustment
        # Lower confidence = reduce Kelly fraction
        confidence_adjusted_kelly = kelly_full * confidence
        
        # Apply fractional Kelly (quarter Kelly by default)
        final_kelly = confidence_adjusted_kelly * fractional_kelly
        
        # Cap at maximum 10% of bankroll
        max_stake_percent = 10.0
        final_kelly = min(final_kelly, max_stake_percent / 100)
        
        # Calculate recommended stake
        recommended_stake = final_kelly * bankroll
        recommended_stake_percent = final_kelly * 100
        
        # Determine if trade is recommended
        min_edge_threshold = 0.03  # 3% minimum edge
        min_ev_threshold = 3.0  # 3 cents EV per dollar
        
        should_trade = (
            edge > min_edge_threshold and 
            ev_cents > min_ev_threshold and 
            final_kelly > 0.001  # At least 0.1% stake
        )
        
        # Build result
        result = {
            "position_analysis": {
                "our_probability": round(p, 4),
                "implied_probability": round(implied_prob, 4),
                "edge": round(edge, 4),
                "edge_percent": round(edge_percent, 2),
                "expected_value_cents": round(ev_cents, 2),
                "market_price": market_price,
                "side": side
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
    Useful for comparing edge across different markets for the same event.
    
    Input:
        markets: List of market objects with our_prob, market_price, side, ticker
        confidence: Overall model confidence
        bankroll: Total bankroll
        
    Output:
        Ranked list of markets by expected value
    """
    try:
        # Parse request_data
        if isinstance(request_data, str):
            try:
                request_data = json.loads(request_data)
            except:
                pass
        
        if not isinstance(request_data, dict):
            request_data = {}
        
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
            
            # Call single Kelly analysis
            analysis = calculate_kelly_position({
                'params': {
                    'our_prob': our_prob,
                    'market_price': market_price,
                    'confidence': confidence,
                    'bankroll': bankroll,
                    'side': side
                }
            })
            
            if analysis.get('status'):
                data = analysis.get('data', {})
                results.append({
                    'ticker': ticker,
                    'market_type': market_type,
                    'yes_subtitle': yes_subtitle,
                    'side': side,
                    'our_prob': our_prob,
                    'market_price': market_price,
                    'edge_percent': data.get('position_analysis', {}).get('edge_percent', 0),
                    'ev_cents': data.get('position_analysis', {}).get('expected_value_cents', 0),
                    'kelly_percent': data.get('stake_recommendation', {}).get('recommended_stake_percent', 0),
                    'should_trade': data.get('trading_decision', {}).get('should_trade', False),
                    'full_analysis': data
                })
        
        # Sort by expected value (highest first)
        results.sort(key=lambda x: x.get('ev_cents', 0), reverse=True)
        
        # Find best trade
        tradeable = [r for r in results if r.get('should_trade')]
        best_trade = tradeable[0] if tradeable else None
        
        return {
            "status": True,
            "data": {
                "markets_analyzed": len(results),
                "tradeable_count": len(tradeable),
                "best_trade": best_trade,
                "all_markets_ranked": results
            },
            "message": f"Analyzed {len(results)} markets, {len(tradeable)} tradeable"
        }
    
    except Exception as e:
        return {
            "status": False,
            "data": {"error": str(e)},
            "message": f"Batch analysis error: {str(e)}"
        }


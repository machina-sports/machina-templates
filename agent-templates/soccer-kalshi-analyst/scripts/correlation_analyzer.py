def analyze_market_correlations(request_data):
    """
    Analyze correlations between prediction market positions and recommend optimal trades.
    Returns in the standard pyscript pattern: {status, data, message}
    
    When multiple markets have positive edge, this function:
    1. Identifies correlated positions (e.g., Team A YES ≈ Team B NO)
    2. Calculates risk-adjusted return for each
    3. Recommends the single best position to avoid double exposure
    
    Risk-Adjusted Return = Edge / Standard Deviation
    Where: Std Dev = sqrt(win_prob × (1 - win_prob))
    
    Parameters:
        kelly_results: Output from batch_kelly_analysis (all_markets_ranked)
        prediction: Dict with home_win_probability, away_win_probability, draw_probability
        home_team: Home team name
        away_team: Away team name
    """
    try:
        # Import inside function to ensure availability in pyscript execution
        import json
        import math
        from collections import Counter
        
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
        kelly_results_raw = params.get('kelly_results', {})
        if not isinstance(kelly_results_raw, dict):
            kelly_results_raw = {}
        
        # Handle nested data structure from connector output
        # Kelly calculator may return data in: root level, 'data' key, or 'kelly_result' key
        kelly_results = kelly_results_raw.get('data', kelly_results_raw)
        if not isinstance(kelly_results, dict):
            kelly_results = kelly_results_raw
        
        # Also check for kelly_result key (some connectors use this)
        if 'kelly_result' in kelly_results_raw:
            kelly_results = kelly_results_raw.get('kelly_result', kelly_results)
        
        prediction = params.get('prediction', {})
        home_team = params.get('home_team', '')
        away_team = params.get('away_team', '')
        
        # Check if Kelly analysis was successful
        if kelly_results_raw.get('status') == False:
            return {
                "status": True,  # Return success but with no correlations
                "data": {
                    "correlated_pairs_detected": False,
                    "correlated_pairs": [],
                    "all_markets_enriched": [],
                    "recommended_trade": None,
                    "recommendation_reason": "kelly_analysis_failed",
                    "trade_recommendation": "Kelly analysis failed - no markets to analyze",
                    "double_exposure_warning": False
                },
                "correlation_analysis": {
                    "correlated_pairs_detected": False,
                    "correlated_pairs": [],
                    "recommended_trade": None,
                    "trade_recommendation": "Kelly analysis failed - no markets to analyze",
                    "double_exposure_warning": False
                },
                "message": "Kelly analysis failed - skipping correlation analysis"
            }
        
        # Get all markets from Kelly results
        all_markets = kelly_results.get('all_markets_ranked', [])
        if not isinstance(all_markets, list):
            all_markets = []
        
        if not all_markets:
            return {
                "status": True,  # Return success with empty results (not an error)
                "data": {
                    "correlated_pairs_detected": False,
                    "correlated_pairs": [],
                    "all_markets_enriched": [],
                    "tradeable_count": 0,
                    "recommended_trade": None,
                    "recommendation_reason": "no_markets",
                    "trade_recommendation": "No markets available for analysis",
                    "double_exposure_warning": False
                },
                "correlation_analysis": {
                    "correlated_pairs_detected": False,
                    "correlated_pairs": [],
                    "recommended_trade": None,
                    "trade_recommendation": "No markets available for analysis",
                    "double_exposure_warning": False
                },
                "message": "No markets to analyze for correlation"
            }
        
        # Helper: Calculate risk-adjusted return
        def calc_risk_adjusted(edge_percent, win_prob):
            """
            Calculate risk-adjusted return (similar to Sharpe ratio).
            Risk-adjusted = edge / standard_deviation
            """
            if win_prob <= 0 or win_prob >= 1:
                return 0
            
            variance = win_prob * (1 - win_prob)
            std_dev = math.sqrt(variance)
            
            if std_dev == 0:
                return 0
            
            # Edge is in percentage points (e.g., 24 for 24%)
            # Convert to decimal for calculation
            edge_decimal = edge_percent / 100
            risk_adjusted = edge_decimal / std_dev
            
            return round(risk_adjusted, 4)
        
        # Helper: Determine correlation between two markets
        def get_correlation_type(market_a, market_b, home_team, away_team):
            """
            Determine if two markets are correlated.
            Returns: ('full', 'partial', 'low', 'none') and explanation
            """
            outcome_a = market_a.get('outcome_type', '')
            outcome_b = market_b.get('outcome_type', '')
            side_a = market_a.get('side', 'yes')
            side_b = market_b.get('side', 'yes')
            
            # Full correlation: Home Win YES ≈ Away Win NO (same outcome, opposite sides)
            # If Team A wins, Team B loses (except draw possibility)
            if outcome_a == 'home_win' and outcome_b == 'away_win':
                if side_a == 'yes' and side_b == 'no':
                    return 'full', 'Home win YES and Away win NO are ~95% correlated'
                if side_a == 'no' and side_b == 'yes':
                    return 'full', 'Home win NO and Away win YES are ~95% correlated'
            
            if outcome_a == 'away_win' and outcome_b == 'home_win':
                if side_a == 'yes' and side_b == 'no':
                    return 'full', 'Away win YES and Home win NO are ~95% correlated'
                if side_a == 'no' and side_b == 'yes':
                    return 'full', 'Away win NO and Home win YES are ~95% correlated'
            
            # Partial correlation: Win YES ≈ Draw NO (~55% correlated)
            if (outcome_a in ['home_win', 'away_win'] and outcome_b == 'draw') or \
               (outcome_a == 'draw' and outcome_b in ['home_win', 'away_win']):
                return 'partial', 'Win and Draw markets are ~55% correlated'
            
            return 'none', 'Markets are independent'
        
        # Step 1: Enrich markets with risk-adjusted return
        enriched_markets = []
        for market in all_markets:
            win_prob = market.get('our_prob', 0.5)
            edge_percent = market.get('edge_percent', 0)
            
            risk_adjusted = calc_risk_adjusted(edge_percent, win_prob)
            
            enriched = {
                **market,
                'win_probability': round(win_prob, 4),
                'variance': round(win_prob * (1 - win_prob), 4),
                'std_dev': round(math.sqrt(win_prob * (1 - win_prob)), 4),
                'risk_adjusted_return': risk_adjusted
            }
            enriched_markets.append(enriched)
        
        # Step 2: Find tradeable markets (positive edge, should_trade=True)
        tradeable = [m for m in enriched_markets if m.get('should_trade', False)]
        
        if len(tradeable) < 2:
            # No correlation analysis needed - 0 or 1 tradeable market
            best = tradeable[0] if tradeable else None
            trade_rec = f"Trade {best['ticker']} ({best.get('side', 'yes').upper()})" if best else "No tradeable opportunities"
            return {
                "status": True,
                "data": {
                    "correlated_pairs_detected": False,
                    "correlated_pairs": [],
                    "all_markets_enriched": enriched_markets,
                    "tradeable_count": len(tradeable),
                    "recommended_trade": best,
                    "recommendation_reason": "single_tradeable" if best else "no_tradeable_markets",
                    "trade_recommendation": trade_rec,
                    "double_exposure_warning": False
                },
                "correlation_analysis": {  # Also at root for easy extraction
                    "correlated_pairs_detected": False,
                    "correlated_pairs": [],
                    "recommended_trade": best,
                    "trade_recommendation": trade_rec,
                    "double_exposure_warning": False
                },
                "message": f"No correlation analysis needed - {len(tradeable)} tradeable market(s)"
            }
        
        # Step 3: Check all pairs for correlation
        correlated_pairs = []
        
        for i, market_a in enumerate(tradeable):
            for j, market_b in enumerate(tradeable):
                if i >= j:  # Skip self-comparisons and duplicates
                    continue
                
                correlation_type, correlation_reason = get_correlation_type(
                    market_a, market_b, home_team, away_team
                )
                
                if correlation_type in ['full', 'partial']:
                    # Determine which market is better
                    rar_a = market_a['risk_adjusted_return']
                    rar_b = market_b['risk_adjusted_return']
                    edge_a = market_a['edge_percent']
                    edge_b = market_b['edge_percent']
                    coverage_a = market_a['win_probability']
                    coverage_b = market_b['win_probability']
                    
                    edge_diff = abs(edge_a - edge_b)
                    coverage_diff = abs(coverage_b - coverage_a) * 100  # Convert to percentage points
                    
                    # Decision logic
                    if edge_diff <= 5 and coverage_diff >= 20:
                        # Small edge sacrifice for much better coverage
                        if coverage_b > coverage_a:
                            recommended = market_b
                            reason = 'higher_coverage'
                            explanation = f"Sacrificing {edge_diff:.1f}% edge for {coverage_diff:.0f}% more coverage"
                        else:
                            recommended = market_a
                            reason = 'higher_coverage'
                            explanation = f"Sacrificing {edge_diff:.1f}% edge for {coverage_diff:.0f}% more coverage"
                    elif edge_diff > 10:
                        # Large edge difference - take the higher edge
                        if edge_a > edge_b:
                            recommended = market_a
                            reason = 'higher_edge'
                            explanation = f"Edge advantage ({edge_a:.1f}% vs {edge_b:.1f}%) outweighs coverage"
                        else:
                            recommended = market_b
                            reason = 'higher_edge'
                            explanation = f"Edge advantage ({edge_b:.1f}% vs {edge_a:.1f}%) outweighs coverage"
                    else:
                        # Use risk-adjusted return as tiebreaker
                        if rar_a > rar_b:
                            recommended = market_a
                            reason = 'higher_risk_adjusted'
                            explanation = f"Better risk-adjusted return ({rar_a:.3f} vs {rar_b:.3f})"
                        else:
                            recommended = market_b
                            reason = 'higher_risk_adjusted'
                            explanation = f"Better risk-adjusted return ({rar_b:.3f} vs {rar_a:.3f})"
                    
                    correlated_pairs.append({
                        'market_a': {
                            'ticker': market_a['ticker'],
                            'side': market_a.get('side', 'yes'),
                            'outcome_type': market_a.get('outcome_type', 'unknown'),
                            'edge_percent': edge_a,
                            'win_probability': coverage_a,
                            'risk_adjusted_return': rar_a
                        },
                        'market_b': {
                            'ticker': market_b['ticker'],
                            'side': market_b.get('side', 'yes'),
                            'outcome_type': market_b.get('outcome_type', 'unknown'),
                            'edge_percent': edge_b,
                            'win_probability': coverage_b,
                            'risk_adjusted_return': rar_b
                        },
                        'correlation_level': correlation_type,
                        'correlation_reason': correlation_reason,
                        'recommended_ticker': recommended['ticker'],
                        'recommendation_reason': reason,
                        'recommendation_explanation': explanation,
                        'edge_difference': round(edge_diff, 2),
                        'coverage_difference': round(coverage_diff, 1)
                    })
        
        # Step 4: Determine final recommendation
        if correlated_pairs:
            # Find the best market considering correlations
            # Prefer markets that appear as "recommended" in correlation analysis
            recommended_tickers = [p['recommended_ticker'] for p in correlated_pairs]
            
            # If one market is consistently recommended, use it
            ticker_counts = Counter(recommended_tickers)
            most_recommended = ticker_counts.most_common(1)[0][0] if ticker_counts else None
            
            best_trade = next((m for m in enriched_markets if m['ticker'] == most_recommended), None)
            
            # Build human-readable recommendation
            if best_trade:
                trade_recommendation = (
                    f"Trade {best_trade['ticker']} ({best_trade.get('side', 'yes').upper()}): "
                    f"{best_trade['edge_percent']:.1f}% edge, "
                    f"{best_trade['win_probability']*100:.0f}% win probability, "
                    f"risk-adjusted return {best_trade['risk_adjusted_return']:.3f}"
                )
            else:
                trade_recommendation = "Unable to determine best trade"
        else:
            # No correlations found - use highest risk-adjusted return
            best_trade = max(tradeable, key=lambda x: x['risk_adjusted_return'])
            trade_recommendation = (
                f"Trade {best_trade['ticker']} ({best_trade.get('side', 'yes').upper()}): "
                f"Best risk-adjusted return ({best_trade['risk_adjusted_return']:.3f})"
            )
        
        return {
            "status": True,
            "data": {
                "correlated_pairs_detected": len(correlated_pairs) > 0,
                "correlated_pairs": correlated_pairs,
                "all_markets_enriched": enriched_markets,
                "tradeable_count": len(tradeable),
                "recommended_trade": best_trade,
                "trade_recommendation": trade_recommendation,
                "double_exposure_warning": len(correlated_pairs) > 0,
                "warning_message": (
                    "CORRELATED POSITIONS DETECTED: Do NOT bet multiple correlated markets. "
                    "Choose the recommended single position to avoid double exposure."
                ) if correlated_pairs else None
            },
            "correlation_analysis": {  # Also at root for easy extraction
                "correlated_pairs_detected": len(correlated_pairs) > 0,
                "correlated_pairs": correlated_pairs,
                "recommended_trade": best_trade,
                "trade_recommendation": trade_recommendation,
                "double_exposure_warning": len(correlated_pairs) > 0
            },
            "message": f"Correlation analysis complete: {len(correlated_pairs)} correlated pair(s) found"
        }
    
    except Exception as e:
        return {
            "status": False,
            "data": {"error": str(e)},
            "message": f"Correlation analysis error: {str(e)}"
        }


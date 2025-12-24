import json
from datetime import datetime


def calculate_audit_metrics(request_data):
    """
    Calculate prediction audit metrics including Brier score and calibration data.
    Returns in the standard pyscript pattern: {status, data, message}
    
    Input:
        prediction: The prediction document with probabilities
        actual_result: The actual match result (home_goals, away_goals)
    
    Output:
        brier_score_components: Individual Brier score for each outcome
        calibration_bin: Which probability bin this prediction falls into
        prediction_correct: Boolean for each outcome type
        roi_data: Data for ROI calculation if bet was placed
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
        
        prediction = params.get('prediction', {})
        actual_result = params.get('actual_result', {})
        edge_analysis = params.get('edge_analysis', {})
        
        if not prediction or not actual_result:
            return {
                "status": False,
                "data": {"error": "Missing prediction or actual_result"},
                "message": "Missing required inputs"
            }
        
        # Extract predicted probabilities
        pred_probs = prediction.get('prediction', prediction)
        home_win_prob = float(pred_probs.get('home_win_probability', 0.33))
        draw_prob = float(pred_probs.get('draw_probability', 0.33))
        away_win_prob = float(pred_probs.get('away_win_probability', 0.34))
        over_2_5_prob = float(pred_probs.get('over_2_5_probability', 0.5))
        under_2_5_prob = float(pred_probs.get('under_2_5_probability', 0.5))
        confidence = float(pred_probs.get('confidence', prediction.get('confidence', 0.5)))
        
        # Extract actual result
        home_goals = int(actual_result.get('home_goals', actual_result.get('goals', {}).get('home', 0)))
        away_goals = int(actual_result.get('away_goals', actual_result.get('goals', {}).get('away', 0)))
        total_goals = home_goals + away_goals
        
        # Determine actual outcomes (1 if true, 0 if false)
        actual_home_win = 1 if home_goals > away_goals else 0
        actual_draw = 1 if home_goals == away_goals else 0
        actual_away_win = 1 if home_goals < away_goals else 0
        actual_over_2_5 = 1 if total_goals > 2.5 else 0
        actual_under_2_5 = 1 if total_goals <= 2.5 else 0
        
        # Calculate Brier score components
        # Brier score = (predicted_prob - actual_outcome)^2
        brier_home = (home_win_prob - actual_home_win) ** 2
        brier_draw = (draw_prob - actual_draw) ** 2
        brier_away = (away_win_prob - actual_away_win) ** 2
        brier_over = (over_2_5_prob - actual_over_2_5) ** 2
        brier_under = (under_2_5_prob - actual_under_2_5) ** 2
        
        # Combined Brier score for 1X2 market (average of three outcomes)
        brier_1x2 = (brier_home + brier_draw + brier_away) / 3
        
        # Determine which outcome was predicted (highest probability)
        probs = {'home': home_win_prob, 'draw': draw_prob, 'away': away_win_prob}
        predicted_outcome = max(probs, key=probs.get)
        predicted_prob = probs[predicted_outcome]
        
        # Determine actual outcome
        if actual_home_win:
            actual_outcome = 'home'
        elif actual_draw:
            actual_outcome = 'draw'
        else:
            actual_outcome = 'away'
        
        prediction_correct = predicted_outcome == actual_outcome
        
        # Calibration bin (for grouping predictions by confidence level)
        # Bins: 0-10%, 10-20%, ..., 90-100%
        calibration_bin = min(int(predicted_prob * 10), 9)  # 0-9
        calibration_bin_label = f"{calibration_bin * 10}-{(calibration_bin + 1) * 10}%"
        
        # ROI calculation if edge analysis exists
        roi_data = None
        if edge_analysis and edge_analysis.get('should_trade'):
            selected = edge_analysis.get('selected_market', edge_analysis.get('selected', {}))
            if selected:
                ticker = selected.get('ticker', '')
                side = selected.get('side', '')
                market_price = float(selected.get('market_price', 50))
                tier = selected.get('tier', 'PASS')
                
                # Determine if the bet won
                bet_won = False
                if 'home' in ticker.lower() or 'avl' in ticker.lower() or 'mun' in ticker.lower():
                    # This is a team-specific market
                    if side == 'yes' and actual_home_win:
                        bet_won = True
                    elif side == 'no' and not actual_home_win:
                        bet_won = True
                
                # Calculate ROI (simplified)
                # If bet won: profit = (100 / market_price) - 1
                # If bet lost: profit = -1 (lost stake)
                if bet_won:
                    roi_percent = ((100 / market_price) - 1) * 100
                else:
                    roi_percent = -100
                
                roi_data = {
                    "ticker": ticker,
                    "side": side,
                    "market_price": market_price,
                    "tier": tier,
                    "bet_won": bet_won,
                    "roi_percent": round(roi_percent, 2)
                }
        
        # Build audit result
        audit_result = {
            "prediction_id": prediction.get('_id', prediction.get('fixture_id', 'unknown')),
            "fixture_id": prediction.get('fixture_id', ''),
            "matchup": prediction.get('matchup', ''),
            "match_date": prediction.get('match_date', ''),
            
            # Actual result
            "actual_result": {
                "home_goals": home_goals,
                "away_goals": away_goals,
                "total_goals": total_goals,
                "outcome": actual_outcome
            },
            
            # Predicted probabilities
            "predicted_probabilities": {
                "home_win": round(home_win_prob, 4),
                "draw": round(draw_prob, 4),
                "away_win": round(away_win_prob, 4),
                "over_2_5": round(over_2_5_prob, 4),
                "under_2_5": round(under_2_5_prob, 4)
            },
            
            # Brier score components
            "brier_scores": {
                "home_win": round(brier_home, 4),
                "draw": round(brier_draw, 4),
                "away_win": round(brier_away, 4),
                "over_2_5": round(brier_over, 4),
                "under_2_5": round(brier_under, 4),
                "combined_1x2": round(brier_1x2, 4)
            },
            
            # Calibration data
            "calibration": {
                "predicted_outcome": predicted_outcome,
                "predicted_probability": round(predicted_prob, 4),
                "actual_outcome": actual_outcome,
                "prediction_correct": prediction_correct,
                "calibration_bin": calibration_bin,
                "calibration_bin_label": calibration_bin_label
            },
            
            # Confidence
            "confidence": round(confidence, 4),
            "abstain_recommended": prediction.get('abstain_recommended', False),
            
            # ROI data (if applicable)
            "roi_data": roi_data,
            
            # Timestamp
            "audit_timestamp": datetime.utcnow().isoformat()
        }
        
        return {
            "status": True,
            "data": {
                "audit_result": audit_result
            },
            "message": "Audit metrics calculated successfully"
        }
    
    except Exception as e:
        return {
            "status": False,
            "data": {"error": str(e)},
            "message": f"Audit calculation error: {str(e)}"
        }


def aggregate_audit_metrics(request_data):
    """
    Aggregate multiple audit results into a backtesting report.
    Returns in the standard pyscript pattern: {status, data, message}
    
    Input:
        audit_results: List of individual audit results
    
    Output:
        overall_brier_score: Average Brier score across all predictions
        calibration_curve: Predicted vs actual by bin
        roi_by_tier: ROI breakdown by tier
        summary_statistics: Overall performance metrics
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
        
        audit_results = params.get('audit_results', [])
        
        if not audit_results:
            return {
                "status": False,
                "data": {"error": "No audit results provided"},
                "message": "No audit results to aggregate"
            }
        
        # Initialize aggregation containers
        brier_scores_1x2 = []
        brier_scores_over = []
        
        # Calibration bins: 10 bins (0-10%, 10-20%, ..., 90-100%)
        calibration_bins = {i: {"predicted_sum": 0, "actual_sum": 0, "count": 0} for i in range(10)}
        
        # ROI by tier
        roi_by_tier = {"A": [], "B": [], "C": [], "PASS": []}
        
        # Accuracy tracking
        correct_predictions = 0
        total_predictions = 0
        
        # Process each audit result
        for audit in audit_results:
            if not isinstance(audit, dict):
                continue
            
            # Handle nested value structure from document storage
            if 'value' in audit:
                audit = audit.get('value', audit)
            
            # Brier scores
            brier = audit.get('brier_scores', {})
            if brier.get('combined_1x2') is not None:
                brier_scores_1x2.append(brier['combined_1x2'])
            if brier.get('over_2_5') is not None:
                brier_scores_over.append(brier['over_2_5'])
            
            # Calibration
            calib = audit.get('calibration', {})
            bin_idx = calib.get('calibration_bin', 0)
            if 0 <= bin_idx < 10:
                calibration_bins[bin_idx]["predicted_sum"] += calib.get('predicted_probability', 0)
                calibration_bins[bin_idx]["actual_sum"] += 1 if calib.get('prediction_correct', False) else 0
                calibration_bins[bin_idx]["count"] += 1
            
            # Accuracy
            if calib.get('prediction_correct') is not None:
                total_predictions += 1
                if calib.get('prediction_correct'):
                    correct_predictions += 1
            
            # ROI by tier
            roi_data = audit.get('roi_data')
            if roi_data:
                tier = roi_data.get('tier', 'PASS')
                if tier in roi_by_tier:
                    roi_by_tier[tier].append(roi_data.get('roi_percent', 0))
        
        # Calculate averages
        avg_brier_1x2 = sum(brier_scores_1x2) / len(brier_scores_1x2) if brier_scores_1x2 else None
        avg_brier_over = sum(brier_scores_over) / len(brier_scores_over) if brier_scores_over else None
        accuracy = correct_predictions / total_predictions if total_predictions > 0 else None
        
        # Build calibration curve
        calibration_curve = []
        total_calibration_error = 0
        for bin_idx in range(10):
            bin_data = calibration_bins[bin_idx]
            if bin_data["count"] > 0:
                avg_predicted = bin_data["predicted_sum"] / bin_data["count"]
                actual_rate = bin_data["actual_sum"] / bin_data["count"]
                calibration_error = abs(avg_predicted - actual_rate)
                total_calibration_error += calibration_error * bin_data["count"]
            else:
                avg_predicted = None
                actual_rate = None
                calibration_error = None
            
            calibration_curve.append({
                "bin": f"{bin_idx * 10}-{(bin_idx + 1) * 10}%",
                "bin_index": bin_idx,
                "count": bin_data["count"],
                "avg_predicted_probability": round(avg_predicted, 4) if avg_predicted is not None else None,
                "actual_success_rate": round(actual_rate, 4) if actual_rate is not None else None,
                "calibration_error": round(calibration_error, 4) if calibration_error is not None else None
            })
        
        avg_calibration_error = total_calibration_error / total_predictions if total_predictions > 0 else None
        
        # Calculate ROI by tier
        roi_summary = {}
        for tier, rois in roi_by_tier.items():
            if rois:
                roi_summary[tier] = {
                    "count": len(rois),
                    "avg_roi_percent": round(sum(rois) / len(rois), 2),
                    "total_roi_percent": round(sum(rois), 2),
                    "win_rate": round(sum(1 for r in rois if r > 0) / len(rois) * 100, 1)
                }
            else:
                roi_summary[tier] = {
                    "count": 0,
                    "avg_roi_percent": None,
                    "total_roi_percent": None,
                    "win_rate": None
                }
        
        # Build report
        report = {
            "report_timestamp": datetime.utcnow().isoformat(),
            "total_predictions": total_predictions,
            
            "brier_scores": {
                "avg_1x2": round(avg_brier_1x2, 4) if avg_brier_1x2 is not None else None,
                "avg_over_2_5": round(avg_brier_over, 4) if avg_brier_over is not None else None,
                "baseline_random": 0.25,  # Random guessing baseline
                "is_better_than_random": avg_brier_1x2 < 0.25 if avg_brier_1x2 is not None else None
            },
            
            "accuracy": {
                "correct_predictions": correct_predictions,
                "total_predictions": total_predictions,
                "accuracy_percent": round(accuracy * 100, 1) if accuracy is not None else None
            },
            
            "calibration": {
                "avg_calibration_error": round(avg_calibration_error, 4) if avg_calibration_error is not None else None,
                "curve": calibration_curve
            },
            
            "roi_by_tier": roi_summary,
            
            "sample_size_sufficient": total_predictions >= 50,
            "recommendation": _get_recommendation(avg_brier_1x2, avg_calibration_error, roi_summary, total_predictions)
        }
        
        return {
            "status": True,
            "data": {
                "backtesting_report": report
            },
            "message": f"Aggregated {total_predictions} predictions into backtesting report"
        }
    
    except Exception as e:
        return {
            "status": False,
            "data": {"error": str(e)},
            "message": f"Aggregation error: {str(e)}"
        }


def _get_recommendation(brier, calib_error, roi_summary, sample_size):
    """Generate a recommendation based on metrics."""
    if sample_size < 50:
        return "Insufficient sample size. Need at least 50 predictions for reliable analysis."
    
    issues = []
    positives = []
    
    # Check Brier score (target < 0.23, random is 0.25)
    if brier is not None:
        if brier >= 0.25:
            issues.append("Brier score >= 0.25 (worse than random)")
        elif brier >= 0.23:
            issues.append("Brier score above target (0.23)")
        else:
            positives.append(f"Brier score {brier:.4f} is below target")
    
    # Check calibration (target < 5%)
    if calib_error is not None:
        if calib_error > 0.10:
            issues.append("High calibration error (>10%)")
        elif calib_error > 0.05:
            issues.append("Calibration error above target (5%)")
        else:
            positives.append(f"Calibration error {calib_error:.4f} is acceptable")
    
    # Check Tier A ROI (target > 5%)
    tier_a = roi_summary.get("A", {})
    if tier_a.get("count", 0) >= 10:
        if tier_a.get("avg_roi_percent", 0) > 5:
            positives.append(f"Tier A ROI is {tier_a['avg_roi_percent']:.1f}%")
        elif tier_a.get("avg_roi_percent", 0) < 0:
            issues.append(f"Tier A ROI is negative ({tier_a['avg_roi_percent']:.1f}%)")
    
    if not issues and positives:
        return "Model performing well. " + " ".join(positives)
    elif issues:
        return "Issues found: " + "; ".join(issues)
    else:
        return "Insufficient data for recommendation."


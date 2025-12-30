def run_monte_carlo_simulation(request_data):
    """
    Run Monte Carlo simulation for soccer using Poisson Distribution with Dixon-Coles adjustment.
    Returns in the standard pyscript pattern: {status, data, message}
    
    The Dixon-Coles model addresses the correlation between low-scoring games by
    adjusting probabilities for scorelines 0-0, 0-1, 1-0, and 1-1 using a rho parameter.
    
    Parameters:
        simulation_parameters:
            home_expected_goals: Expected goals for home team
            away_expected_goals: Expected goals for away team
            correlation_rho: Dixon-Coles rho (-0.15 to 0), default 0 (no adjustment)
        num_simulations: Number of simulations to run (default 10000)
    """
    try:
        # Import inside function to ensure availability in pyscript execution
        import json
        
        # Try importing numpy and scipy
        try:
            import numpy as np
            from scipy.stats import poisson
            HAS_SCIPY = True
        except ImportError:
            HAS_SCIPY = False
            import random
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
        
        sim_params = params.get('simulation_parameters', {})
        num_simulations = params.get('num_simulations', 10000)

        if not isinstance(sim_params, dict) or not sim_params:
            return {
                "status": False,
                "data": {"simulation_results": {}, "error": "No simulation parameters provided"},
                "message": "No simulation parameters provided"
            }

        # Handle potential string/None values
        home_exp_goals = sim_params.get('home_expected_goals')
        if home_exp_goals is None:
            home_exp_goals = 1.5
        else:
            home_exp_goals = float(home_exp_goals)
        
        away_exp_goals = sim_params.get('away_expected_goals')
        if away_exp_goals is None:
            away_exp_goals = 1.2
        else:
            away_exp_goals = float(away_exp_goals)
        
        # Dixon-Coles correlation parameter (backwards compatible - default 0)
        rho = sim_params.get('correlation_rho')
        if rho is None:
            rho = 0.0  # No adjustment by default for backwards compatibility
        else:
            rho = float(rho)
            # Clamp rho to valid range
            rho = max(-0.20, min(0.0, rho))

        num_simulations = int(num_simulations)
        
        # Dixon-Coles tau function for low-scoring adjustments
        def dixon_coles_tau(home, away, lambda_h, lambda_a, rho):
            """
            Calculate the Dixon-Coles adjustment factor for low-scoring games.
            Only applies to scorelines 0-0, 0-1, 1-0, 1-1.
            Returns 1.0 for all other scorelines (no adjustment).
            
            Args:
                home: Home team score
                away: Away team score
                lambda_h: Home expected goals
                lambda_a: Away expected goals
                rho: Correlation coefficient (typically -0.10 to -0.15 for football)
            """
            if rho == 0:
                return 1.0
            
            if home == 0 and away == 0:
                return 1 - lambda_h * lambda_a * rho
            elif home == 0 and away == 1:
                return 1 + lambda_h * rho
            elif home == 1 and away == 0:
                return 1 + lambda_a * rho
            elif home == 1 and away == 1:
                return 1 - rho
            return 1.0

        # Generate Poisson-distributed random variates with Dixon-Coles adjustment
        if HAS_SCIPY:
            # Calculate base Poisson probabilities for each scoreline
            max_goals = 10
            home_probs = poisson.pmf(range(max_goals + 1), home_exp_goals)
            away_probs = poisson.pmf(range(max_goals + 1), away_exp_goals)
            
            # Build joint probability matrix with Dixon-Coles adjustment
            joint_probs = np.zeros((max_goals + 1, max_goals + 1))
            for h in range(max_goals + 1):
                for a in range(max_goals + 1):
                    tau = dixon_coles_tau(h, a, home_exp_goals, away_exp_goals, rho)
                    joint_probs[h, a] = home_probs[h] * away_probs[a] * tau
            
            # Normalize to ensure probabilities sum to 1
            joint_probs = joint_probs / joint_probs.sum()
            
            # Sample from the joint distribution
            flat_probs = joint_probs.flatten()
            indices = np.random.choice(len(flat_probs), size=num_simulations, p=flat_probs)
            home_scores = indices // (max_goals + 1)
            away_scores = indices % (max_goals + 1)
            
            # Calculate probabilities efficiently
            home_wins = int(np.sum(home_scores > away_scores))
            draws = int(np.sum(home_scores == away_scores))
            away_wins = int(np.sum(home_scores < away_scores))
            total_goals = home_scores + away_scores
            over_2_5 = int(np.sum(total_goals > 2.5))
            under_2_5 = int(np.sum(total_goals <= 2.5))
            
            # Calculate exact scoreline probabilities for common markets
            exact_00 = float(joint_probs[0, 0])
            exact_11 = float(joint_probs[1, 1])
            exact_10 = float(joint_probs[1, 0])
            exact_01 = float(joint_probs[0, 1])
            exact_21 = float(joint_probs[2, 1])
            exact_12 = float(joint_probs[1, 2])
            exact_20 = float(joint_probs[2, 0])
            exact_02 = float(joint_probs[0, 2])
            
        else:
            # Fallback: Pure Python simulation with Dixon-Coles
            import math
            import random
            
            def poisson_pmf(k, lam):
                """Calculate Poisson probability mass function."""
                return (lam ** k) * math.exp(-lam) / math.factorial(k)
            
            # Build joint probability matrix
            max_goals = 10
            joint_probs = []
            total_prob = 0
            
            for h in range(max_goals + 1):
                row = []
                for a in range(max_goals + 1):
                    p_h = poisson_pmf(h, home_exp_goals)
                    p_a = poisson_pmf(a, away_exp_goals)
                    tau = dixon_coles_tau(h, a, home_exp_goals, away_exp_goals, rho)
                    prob = p_h * p_a * tau
                    row.append(prob)
                    total_prob += prob
                joint_probs.append(row)
            
            # Normalize
            for h in range(max_goals + 1):
                for a in range(max_goals + 1):
                    joint_probs[h][a] /= total_prob
            
            # Build CDF for sampling
            flat_probs = []
            for h in range(max_goals + 1):
                for a in range(max_goals + 1):
                    flat_probs.append(joint_probs[h][a])
            
            cumulative = []
            running = 0
            for p in flat_probs:
                running += p
                cumulative.append(running)
            
            # Sample from distribution
            home_wins = 0
            draws = 0
            away_wins = 0
            over_2_5 = 0
            under_2_5 = 0
            
            for _ in range(num_simulations):
                r = random.random()
                idx = 0
                for i, c in enumerate(cumulative):
                    if r <= c:
                        idx = i
                        break
                
                h = idx // (max_goals + 1)
                a = idx % (max_goals + 1)
                total = h + a
                
                if h > a:
                    home_wins += 1
                elif h < a:
                    away_wins += 1
                else:
                    draws += 1
                
                if total > 2.5:
                    over_2_5 += 1
                else:
                    under_2_5 += 1
            
            # Exact scoreline probabilities
            exact_00 = joint_probs[0][0]
            exact_11 = joint_probs[1][1]
            exact_10 = joint_probs[1][0]
            exact_01 = joint_probs[0][1]
            exact_21 = joint_probs[2][1]
            exact_12 = joint_probs[1][2]
            exact_20 = joint_probs[2][0]
            exact_02 = joint_probs[0][2]

        # Calculate probabilities
        home_win_prob = home_wins / num_simulations
        draw_prob = draws / num_simulations
        away_win_prob = away_wins / num_simulations
        over_2_5_prob = over_2_5 / num_simulations
        under_2_5_prob = under_2_5 / num_simulations

        # Build result
        simulation_results = {
            "home_win_probability": round(home_win_prob, 4),
            "draw_probability": round(draw_prob, 4),
            "away_win_probability": round(away_win_prob, 4),
            "over_2_5_prob": round(over_2_5_prob, 4),
            "under_2_5_prob": round(under_2_5_prob, 4),
            "exact_scorelines": {
                "0-0": round(exact_00, 4),
                "1-1": round(exact_11, 4),
                "1-0": round(exact_10, 4),
                "0-1": round(exact_01, 4),
                "2-1": round(exact_21, 4),
                "1-2": round(exact_12, 4),
                "2-0": round(exact_20, 4),
                "0-2": round(exact_02, 4)
            },
            "inputs": {
                "home_expected_goals": home_exp_goals,
                "away_expected_goals": away_exp_goals,
                "correlation_rho": rho,
                "num_simulations": num_simulations
            },
            "method": "dixon_coles_scipy" if HAS_SCIPY else "dixon_coles_python",
            "simulations_run": num_simulations
        }

        return {
            "status": True,
            "data": {
                "simulation_results": simulation_results
            },
            "message": f"Monte Carlo simulation completed with {num_simulations} iterations (Dixon-Coles rho={rho})"
        }

    except Exception as e:
        return {
            "status": False,
            "data": {"simulation_results": {}, "error": str(e)},
            "message": f"Monte Carlo Exception: {str(e)}"
        }

def run_monte_carlo_simulation(request_data):
    """
    Run Monte Carlo simulation for soccer using Poisson Distribution.
    Returns in the standard pyscript pattern: {status, data, message}
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

        num_simulations = int(num_simulations)

        # Generate Poisson-distributed random variates
        if HAS_SCIPY:
            # Use scipy/numpy for efficient simulation
            home_scores = np.random.poisson(home_exp_goals, num_simulations)
            away_scores = np.random.poisson(away_exp_goals, num_simulations)
            
            # Calculate probabilities efficiently
            home_wins = int(np.sum(home_scores > away_scores))
            draws = int(np.sum(home_scores == away_scores))
            away_wins = int(np.sum(home_scores < away_scores))
            total_goals = home_scores + away_scores
            over_2_5 = int(np.sum(total_goals > 2.5))
            under_2_5 = int(np.sum(total_goals <= 2.5))
        else:
            # Fallback: Pure Python Poisson simulation
            def poisson_random(lam):
                """Generate Poisson random variate using inverse transform"""
                L = math.exp(-lam)
                k = 0
                p = 1.0
                while p > L:
                    k += 1
                    p *= random.random()
                return k - 1
            
            home_wins = 0
            draws = 0
            away_wins = 0
            over_2_5 = 0
            under_2_5 = 0
            
            for _ in range(num_simulations):
                h = poisson_random(home_exp_goals)
                a = poisson_random(away_exp_goals)
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
            "inputs": {
                "home_expected_goals": home_exp_goals,
                "away_expected_goals": away_exp_goals,
                "num_simulations": num_simulations
            },
            "method": "scipy_numpy" if HAS_SCIPY else "pure_python"
        }

        return {
            "status": True,
            "data": {
                "simulation_results": simulation_results
            },
            "message": f"Monte Carlo simulation completed with {num_simulations} iterations"
        }

    except Exception as e:
        return {
            "status": False,
            "data": {"simulation_results": {}, "error": str(e)},
            "message": f"Monte Carlo Exception: {str(e)}"
        }

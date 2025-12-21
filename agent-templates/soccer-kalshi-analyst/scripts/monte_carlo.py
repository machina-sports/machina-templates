import numpy as np
import pandas as pd
from scipy.stats import poisson

def run_monte_carlo_simulation(params):
    """
    Run Monte Carlo simulation for soccer using Poisson Distribution.
    """
    try:
        if isinstance(params, str):
            import json
            params = json.loads(params)
        
        sim_params = params.get('simulation_parameters', {})
        num_simulations = params.get('num_simulations', 10000)

        if not isinstance(sim_params, dict) or not sim_params:
            return {"error": "No simulation parameters provided"}

        # Handle potential string/None values
        home_exp_goals = sim_params.get('home_expected_goals')
        if home_exp_goals is None: home_exp_goals = 1.5
        else: home_exp_goals = float(home_exp_goals)
        
        away_exp_goals = sim_params.get('away_expected_goals')
        if away_exp_goals is None: away_exp_goals = 1.2
        else: away_exp_goals = float(away_exp_goals)

        num_simulations = int(num_simulations)

        # Simple Poisson simulation
        home_scores = np.random.poisson(home_exp_goals, num_simulations)
        away_scores = np.random.poisson(away_exp_goals, num_simulations)

        results = []
        for h, a in zip(home_scores, away_scores):
            results.append({
                'home_goals': int(h),
                'away_goals': int(a),
                'result': 'home' if h > a else ('away' if a > h else 'draw'),
                'total_goals': int(h + a)
            })

        df = pd.DataFrame(results)
        
        return {
            "simulation_results": {
                "home_win_probability": float(len(df[df['result'] == 'home']) / num_simulations),
                "draw_probability": float(len(df[df['result'] == 'draw']) / num_simulations),
                "away_win_probability": float(len(df[df['result'] == 'away']) / num_simulations),
                "over_2_5_prob": float(len(df[df['total_goals'] > 2.5]) / num_simulations),
                "under_2_5_prob": float(len(df[df['total_goals'] < 2.5]) / num_simulations)
            }
        }
    except Exception as e:
        return {"error": f"Monte Carlo Exception: {str(e)}"}

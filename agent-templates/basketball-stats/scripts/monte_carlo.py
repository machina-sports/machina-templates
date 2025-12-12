import numpy as np
import pandas as pd
from scipy import stats
import json

def run_monte_carlo_simulation(params):
    """
    Run Monte Carlo simulation for basketball game forecasting.

    Args:
        params: Dictionary containing:
            - simulation_parameters: LLM-generated parameters
            - num_simulations: Number of simulations to run (default 10000)

    Returns:
        Dictionary with simulation results
    """

    def _correlation_to_covariance(corr_matrix, std_devs):
        """
        Convert correlation matrix to covariance matrix.

        Args:
            corr_matrix: Correlation matrix
            std_devs: Array of standard deviations

        Returns:
            Covariance matrix
        """
        # Create diagonal matrix of variances
        var_matrix = np.diag(std_devs ** 2)

        # Cholesky decomposition of correlation matrix
        chol_corr = np.linalg.cholesky(corr_matrix)

        # Covariance = L * Var * L^T where L is Cholesky decomposition
        cov_matrix = chol_corr @ var_matrix @ chol_corr.T

        return cov_matrix

    sim_params = params.get('simulation_parameters', {})
    num_simulations = params.get('num_simulations', 10000)

    if not sim_params:
        return {"error": "No simulation parameters provided"}

    try:
        # Extract parameters
        latent_params = sim_params.get('latent_parameters', {})
        correlations = sim_params.get('correlations', {})

        pace_mean = latent_params.get('pace_mean', 95.0)
        pace_sd = latent_params.get('pace_sd', 5.0)
        home_off_eff_mean = latent_params.get('home_off_eff_mean', 1.1)
        home_off_eff_sd = latent_params.get('home_off_eff_sd', 0.05)
        away_off_eff_mean = latent_params.get('away_off_eff_mean', 1.05)
        away_off_eff_sd = latent_params.get('away_off_eff_sd', 0.05)
        injury_multiplier = latent_params.get('injury_variance_multiplier', 1.0)

        pace_off_eff_corr = correlations.get('pace_off_eff_corr', 0.0)

        # Apply injury multiplier to variance
        home_off_eff_sd *= injury_multiplier
        away_off_eff_sd *= injury_multiplier

        # Create correlation matrix for pace and efficiencies
        # Variables: [pace, home_off_eff, away_off_eff]
        corr_matrix = np.array([
            [1.0, pace_off_eff_corr, pace_off_eff_corr],
            [pace_off_eff_corr, 1.0, 0.0],  # Assume no correlation between team efficiencies
            [pace_off_eff_corr, 0.0, 1.0]
        ])

        # Create covariance matrix
        std_devs = np.array([pace_sd, home_off_eff_sd, away_off_eff_sd])
        cov_matrix = _correlation_to_covariance(corr_matrix, std_devs)

        # Run simulations
        results = []
        for i in range(num_simulations):
            # Generate correlated random variables
            means = np.array([pace_mean, home_off_eff_mean, away_off_eff_mean])
            simulation_vars = np.random.multivariate_normal(means, cov_matrix)

            pace = max(70, min(130, simulation_vars[0]))  # Clamp to reasonable range
            home_off_eff = max(0.7, min(1.5, simulation_vars[1]))  # Clamp efficiency
            away_off_eff = max(0.7, min(1.5, simulation_vars[2]))

            # Calculate defensive efficiencies (simplified - assume league average defense)
            league_def_eff = 1.08  # Typical NBA defensive efficiency
            home_def_eff = league_def_eff
            away_def_eff = league_def_eff

            # Calculate points scored by each team
            home_points = pace * home_off_eff * (1 / home_def_eff) * 100  # possessions * off_eff * (1/def_eff)
            away_points = pace * away_off_eff * (1 / away_def_eff) * 100

            # Add some randomness for actual scoring vs efficiency
            home_points += np.random.normal(0, 3)
            away_points += np.random.normal(0, 3)

            results.append({
                'home_points': max(60, home_points),  # Minimum realistic score
                'away_points': max(60, away_points),
                'total_points': home_points + away_points,
                'spread_home_minus': home_points - away_points,
                'home_win': home_points > away_points
            })

        # Convert to DataFrame for analysis
        df = pd.DataFrame(results)

        # Calculate summary statistics
        home_win_prob = df['home_win'].mean()
        spread_median = df['spread_home_minus'].median()
        total_median = df['total_points'].median()

        # Calculate quantiles for uncertainty
        spread_q10 = df['spread_home_minus'].quantile(0.1)
        spread_q90 = df['spread_home_minus'].quantile(0.9)
        total_q10 = df['total_points'].quantile(0.1)
        total_q90 = df['total_points'].quantile(0.9)

        # Calculate spreads for quantiles
        spread_q25 = df['spread_home_minus'].quantile(0.25)
        spread_q75 = df['spread_home_minus'].quantile(0.75)

        return {
            "simulation_results": {
                "num_simulations": num_simulations,
                "home_win_probability": float(home_win_prob),
                "spread_median": float(spread_median),
                "total_median": float(total_median),
                "spread_q10": float(spread_q10),
                "spread_q25": float(spread_q25),
                "spread_q75": float(spread_q75),
                "spread_q90": float(spread_q90),
                "total_q10": float(total_q10),
                "total_q90": float(total_q90),
                "spread_std": float(df['spread_home_minus'].std()),
                "total_std": float(df['total_points'].std())
            },
            "simulation_summary": {
                "home_score_mean": float(df['home_points'].mean()),
                "away_score_mean": float(df['away_points'].mean()),
                "home_score_std": float(df['home_points'].std()),
                "away_score_std": float(df['away_points'].std()),
                "upsets": int((df['home_win'] == False).sum()),  # Assuming home is favorite
                "blowouts": int(((df['spread_home_minus'].abs()) > 20).sum())
            }
        }

    except Exception as e:
        return {"error": f"Monte Carlo simulation failed: {str(e)}"}
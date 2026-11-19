
"""Empirical coverage validation for the production Newcombe-Wilson CI."""

from pathlib import Path
import sys

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from experimentation.analyze_event_experiments import compare_variants


SEED = 20261119
SIMULATIONS = 10_000
ALPHA = 0.05
TARGET_COVERAGE = 1 - ALPHA

SCENARIOS = [
    {
        "scenario": "Low conversion",
        "control_rate": 0.02,
        "treatment_rate": 0.02,
        "users_per_variant": 100,
    },
    {
        "scenario": "Moderate conversion",
        "control_rate": 0.20,
        "treatment_rate": 0.20,
        "users_per_variant": 500,
    },
    {
        "scenario": "High conversion",
        "control_rate": 0.70,
        "treatment_rate": 0.70,
        "users_per_variant": 1000,
    },
    {
        "scenario": "Unequal conversion",
        "control_rate": 0.20,
        "treatment_rate": 0.25,
        "users_per_variant": 1000,
    },
]


def validate_scenario(scenario, rng):
    """Estimate empirical CI coverage for one binomial scenario."""

    control_rate = scenario["control_rate"]
    treatment_rate = scenario["treatment_rate"]
    sample_size = scenario["users_per_variant"]

    true_difference_pp = (
        treatment_rate - control_rate
    ) * 100

    covered = 0

    for _ in range(SIMULATIONS):
        control_x = int(
            rng.binomial(sample_size, control_rate)
        )
        treatment_x = int(
            rng.binomial(sample_size, treatment_rate)
        )

        result = compare_variants(
            control_n=sample_size,
            control_x=control_x,
            treatment_n=sample_size,
            treatment_x=treatment_x,
            alpha=ALPHA,
        )

        ci_low = result["confidence_interval_low_pp"]
        ci_high = result["confidence_interval_high_pp"]

        if ci_low <= true_difference_pp <= ci_high:
            covered += 1

    empirical_coverage = covered / SIMULATIONS

    monte_carlo_se = np.sqrt(
        empirical_coverage
        * (1 - empirical_coverage)
        / SIMULATIONS
    )

    # Three standard errors below nominal coverage is the
    # undercoverage screening threshold for this simulation.
    target_mc_se = np.sqrt(
        TARGET_COVERAGE
        * (1 - TARGET_COVERAGE)
        / SIMULATIONS
    )
    minimum_acceptable = TARGET_COVERAGE - 3 * target_mc_se

    return {
        "scenario": scenario["scenario"],
        "control_rate_pct": control_rate * 100,
        "treatment_rate_pct": treatment_rate * 100,
        "users_per_variant": sample_size,
        "simulations": SIMULATIONS,
        "true_difference_pp": true_difference_pp,
        "empirical_coverage_pct": empirical_coverage * 100,
        "target_coverage_pct": TARGET_COVERAGE * 100,
        "monte_carlo_se_pp": monte_carlo_se * 100,
        "minimum_acceptable_coverage_pct": (
            minimum_acceptable * 100
        ),
        "assessment": (
            "PASS"
            if empirical_coverage >= minimum_acceptable
            else "FAIL"
        ),
    }


def main():
    rng = np.random.default_rng(SEED)

    results = [
        validate_scenario(scenario, rng)
        for scenario in SCENARIOS
    ]

    report = pd.DataFrame(results)

    display_columns = [
        "scenario",
        "control_rate_pct",
        "treatment_rate_pct",
        "users_per_variant",
        "empirical_coverage_pct",
        "target_coverage_pct",
        "monte_carlo_se_pp",
        "minimum_acceptable_coverage_pct",
        "assessment",
    ]

    print("\nNEWCOMBE-WILSON CONFIDENCE INTERVAL COVERAGE")
    print("=" * 88)
    print(f"Random seed: {SEED}")
    print(f"Simulations per scenario: {SIMULATIONS:,}")
    print(f"Total simulations: {SIMULATIONS * len(SCENARIOS):,}")
    print(f"Confidence level: {TARGET_COVERAGE:.0%}")
    print("\n" + report[display_columns].to_string(index=False))

    output_path = (
        PROJECT_ROOT
        / "data"
        / "synthetic"
        / "experiment_dataset"
        / "confidence_interval_coverage_validation.csv"
    )

    report.to_csv(output_path, index=False)

    print(f"\nSaved validation report: {output_path}")

    if (report["assessment"] == "FAIL").any():
        print("\nOVERALL ASSESSMENT: FAIL")
        sys.exit(1)

    print("\nOVERALL ASSESSMENT: PASS")


if __name__ == "__main__":
    main()

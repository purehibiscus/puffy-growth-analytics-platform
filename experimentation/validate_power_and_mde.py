
"""Power and MDE validation using the production two-proportion z-test."""

from pathlib import Path
import sys

import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.stats import norm


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from experimentation.analyze_event_experiments import compare_variants


REGISTRY_PATH = PROJECT_ROOT / "data" / "synthetic" / "experiments.csv"
ANALYSIS_PATH = (
    PROJECT_ROOT
    / "data"
    / "synthetic"
    / "experiment_dataset"
    / "event_experiment_analysis.csv"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "synthetic"
    / "experiment_dataset"
    / "power_mde_validation.csv"
)

SEED = 20261120
SIMULATIONS = 5_000
EFFECTS_PP = [2, 4, 6]
SAMPLE_SIZES = [500, 1000, 2000, 5000]
TARGET_POWERS = [0.80, 0.90]


def load_experiment_baselines():
    """Load registered settings and synthetic control-group baselines."""

    registry = pd.read_csv(REGISTRY_PATH)
    analysis = pd.read_csv(ANALYSIS_PATH)

    required_registry = {
        "experiment_id", "alpha", "power", "status"
    }
    required_analysis = {
        "experiment_id", "variant", "denominator_users",
        "conversion_rate_pct",
    }

    if not required_registry.issubset(registry.columns):
        raise ValueError("Experiment registry is missing required columns.")

    if not required_analysis.issubset(analysis.columns):
        raise ValueError("Experiment analysis is missing required columns.")

    controls = analysis.loc[
    analysis["variant"].str.lower() == "control",
    [
        "experiment_id",
        "variant",
        "denominator_users",
        "conversion_rate_pct",
    ],
].copy()

    baselines = controls.merge(
        registry[
            ["experiment_id", "alpha", "power", "status"]
        ],
        on="experiment_id",
        how="inner",
        validate="one_to_one",
    )

    if baselines.empty:
        raise ValueError("No matching control-group baselines found.")

    if baselines["conversion_rate_pct"].isna().any():
        raise ValueError("A control conversion rate is missing.")

    return baselines


def required_sample_size(
    baseline_rate,
    treatment_rate,
    alpha,
    target_power,
):
    """Approximate equal sample size per arm for a two-sided test."""

    if not 0 < baseline_rate < 1:
        raise ValueError("Baseline rate must be between 0 and 1.")

    if not baseline_rate < treatment_rate < 1:
        raise ValueError("Treatment rate must exceed baseline and be below 1.")

    if not 0 < alpha < 1 or not 0 < target_power < 1:
        raise ValueError("Alpha and target power must be between 0 and 1.")

    pooled_rate = (baseline_rate + treatment_rate) / 2

    z_alpha = norm.ppf(1 - alpha / 2)
    z_power = norm.ppf(target_power)

    null_component = np.sqrt(
        2 * pooled_rate * (1 - pooled_rate)
    )

    alternative_component = np.sqrt(
        baseline_rate * (1 - baseline_rate)
        + treatment_rate * (1 - treatment_rate)
    )

    difference = treatment_rate - baseline_rate

    sample_size = (
        z_alpha * null_component
        + z_power * alternative_component
    ) ** 2 / difference**2

    return int(np.ceil(sample_size))


def calculate_mde(
    baseline_rate,
    sample_size,
    alpha,
    target_power,
):
    """Find the approximate positive absolute MDE per variant."""

    maximum_effect = 1 - baseline_rate - 1e-8

    def difference_from_target(effect):
        treatment_rate = baseline_rate + effect

        return required_sample_size(
            baseline_rate,
            treatment_rate,
            alpha,
            target_power,
        ) - sample_size

    return brentq(
        difference_from_target,
        1e-8,
        maximum_effect,
    )


def simulate_power(
    baseline_rate,
    treatment_rate,
    sample_size,
    alpha,
    rng,
):
    """Estimate power by repeatedly calling the production test."""

    significant = 0

    for _ in range(SIMULATIONS):
        control_x = int(
            rng.binomial(sample_size, baseline_rate)
        )

        treatment_x = int(
            rng.binomial(sample_size, treatment_rate)
        )

        result = compare_variants(
            control_n=sample_size,
            control_x=control_x,
            treatment_n=sample_size,
            treatment_x=treatment_x,
            alpha=alpha,
        )

        significant += result["statistically_significant"]

    empirical_power = significant / SIMULATIONS

    monte_carlo_se = np.sqrt(
        empirical_power * (1 - empirical_power) / SIMULATIONS
    )

    return empirical_power, monte_carlo_se


def main():
    rng = np.random.default_rng(SEED)
    baselines = load_experiment_baselines()

    results = []

    for _, experiment in baselines.iterrows():
        experiment_id = experiment["experiment_id"]
        baseline_rate = float(
            experiment["conversion_rate_pct"]
        ) / 100

        alpha = float(experiment["alpha"])
        registered_power = float(experiment["power"])
        registry_status = experiment["status"]
        observed_n = int(experiment["denominator_users"])

        print(f"\nProcessing {experiment_id}...")
        print(
            f"Baseline: {baseline_rate:.2%} | "
            f"Observed control users: {observed_n}"
        )

        # Part 1: Empirical power at fixed treatment effects.
        for sample_size in SAMPLE_SIZES:
            for effect_pp in EFFECTS_PP:
                treatment_rate = baseline_rate + effect_pp / 100

                if treatment_rate >= 1:
                    continue

                empirical_power, mc_se = simulate_power(
                    baseline_rate,
                    treatment_rate,
                    sample_size,
                    alpha,
                    rng,
                )

                results.append({
                    "experiment_id": experiment_id,
                    "registry_status": registry_status,
                    "analysis_type": "fixed_effect_power",
                    "baseline_conversion_pct": baseline_rate * 100,
                    "sample_size_per_variant": sample_size,
                    "effect_or_mde_pp": effect_pp,
                    "target_power_pct": registered_power * 100,
                    "empirical_power_pct": empirical_power * 100,
                    "monte_carlo_se_pp": mc_se * 100,
                    "assessment": "MEASURED",
                })

        # Part 2: Calculate MDE and validate it empirically.
        for sample_size in SAMPLE_SIZES:
            for target_power in TARGET_POWERS:
                mde = calculate_mde(
                    baseline_rate,
                    sample_size,
                    alpha,
                    target_power,
                )

                treatment_rate = baseline_rate + mde

                empirical_power, mc_se = simulate_power(
                    baseline_rate,
                    treatment_rate,
                    sample_size,
                    alpha,
                    rng,
                )

                # Three nominal Monte Carlo standard errors
                # below the target is the underpowering threshold.
                nominal_mc_se = np.sqrt(
                    target_power * (1 - target_power)
                    / SIMULATIONS
                )

                minimum_acceptable = (
                    target_power - 3 * nominal_mc_se
                )

                assessment = (
                    "PASS"
                    if empirical_power >= minimum_acceptable
                    else "REVIEW"
                )

                results.append({
                    "experiment_id": experiment_id,
                    "registry_status": registry_status,
                    "analysis_type": "mde_validation",
                    "baseline_conversion_pct": baseline_rate * 100,
                    "sample_size_per_variant": sample_size,
                    "effect_or_mde_pp": mde * 100,
                    "target_power_pct": target_power * 100,
                    "empirical_power_pct": empirical_power * 100,
                    "monte_carlo_se_pp": mc_se * 100,
                    "assessment": assessment,
                })

    report = pd.DataFrame(results)
    report.to_csv(OUTPUT_PATH, index=False)

    print("\nPOWER AND MDE VALIDATION")
    print("=" * 100)
    print(f"Random seed: {SEED}")
    print(f"Simulations per scenario: {SIMULATIONS:,}")
    print(f"Total simulation runs: {len(report) * SIMULATIONS:,}")

    for experiment_id in baselines["experiment_id"]:
        experiment_results = report[
            report["experiment_id"] == experiment_id
        ]

        print(f"\n{experiment_id}")
        print("-" * 100)

        print("\nEMPIRICAL POWER AT FIXED EFFECTS")
        fixed_effects = experiment_results[
            experiment_results["analysis_type"] == "fixed_effect_power"
        ]

        print(
            fixed_effects[
                [
                    "sample_size_per_variant",
                    "effect_or_mde_pp",
                    "empirical_power_pct",
                    "target_power_pct",
                ]
            ].to_string(index=False)
        )

        print("\nMDE AND EMPIRICAL VALIDATION")
        mde_results = experiment_results[
            experiment_results["analysis_type"] == "mde_validation"
        ]

        print(
            mde_results[
                [
                    "sample_size_per_variant",
                    "target_power_pct",
                    "effect_or_mde_pp",
                    "empirical_power_pct",
                    "monte_carlo_se_pp",
                    "assessment",
                ]
            ].to_string(index=False)
        )

    print(f"\nSaved report: {OUTPUT_PATH}")

    failed = report.loc[
        report["analysis_type"] == "mde_validation",
        "assessment",
    ].eq("REVIEW").any()

    if failed:
        print("\nOVERALL ASSESSMENT: REVIEW")
    else:
        print("\nOVERALL ASSESSMENT: PASS")


if __name__ == "__main__":
    main()


from pathlib import Path
import sys

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from experimentation.analyze_event_experiments import compare_variants


# ============================================================
# CONFIGURATION
# ============================================================

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "synthetic"
    / "experiment_dataset"
    / "sensitivity_robustness_validation.csv"
)

SEED = 20261121
SIMULATIONS = 5000
ALPHA = 0.05

# Treatment sample size = control sample size * allocation ratio
ALLOCATION_RATIOS = [1.0, 1.5, 2.0]

BASELINE_RATES = [0.05, 0.10, 0.20, 0.40, 0.60]

# Absolute percentage-point improvements
TREATMENT_EFFECTS_PP = [0, 2, 4, 6]

CONTROL_SAMPLE_SIZES = [500, 1000]


# ============================================================
# SIMULATION
# ============================================================

def simulate_scenario(
    baseline_rate,
    treatment_effect_pp,
    control_n,
    treatment_n,
    rng,
):
    treatment_rate = baseline_rate + (
        treatment_effect_pp / 100
    )

    if not 0 < baseline_rate < 1:
        raise ValueError("Baseline rate must be between 0 and 1.")

    if not 0 < treatment_rate < 1:
        raise ValueError(
            "Treatment rate must be between 0 and 1."
        )

    significant_count = 0

    for _ in range(SIMULATIONS):
        control_successes = rng.binomial(
            control_n,
            baseline_rate,
        )

        treatment_successes = rng.binomial(
            treatment_n,
            treatment_rate,
        )

        result = compare_variants(
            control_n=control_n,
            control_x=int(control_successes),
            treatment_n=treatment_n,
            treatment_x=int(treatment_successes),
            alpha=ALPHA,
        )

        if result["statistically_significant"]:
            significant_count += 1

    empirical_rate = significant_count / SIMULATIONS

    monte_carlo_se = np.sqrt(
        empirical_rate * (1 - empirical_rate)
        / SIMULATIONS
    )

    return {
        "significant_count": significant_count,
        "empirical_rate_pct": empirical_rate * 100,
        "monte_carlo_se_pp": monte_carlo_se * 100,
    }


# ============================================================
# VALIDATION
# ============================================================

def run_sensitivity_validation():
    rng = np.random.default_rng(SEED)

    records = []

    total_scenarios = (
        len(BASELINE_RATES)
        * len(ALLOCATION_RATIOS)
        * len(CONTROL_SAMPLE_SIZES)
        * len(TREATMENT_EFFECTS_PP)
    )

    scenario_number = 0

    for baseline in BASELINE_RATES:
        for allocation_ratio in ALLOCATION_RATIOS:
            for control_n in CONTROL_SAMPLE_SIZES:

                treatment_n = int(
                    round(control_n * allocation_ratio)
                )

                for effect_pp in TREATMENT_EFFECTS_PP:
                    scenario_number += 1

                    analysis_type = (
                        "TYPE_I_ERROR"
                        if effect_pp == 0
                        else "STATISTICAL_POWER"
                    )

                    print(
                        f"Scenario {scenario_number}/{total_scenarios}: "
                        f"Baseline={baseline:.0%}, "
                        f"Allocation=1:{allocation_ratio:g}, "
                        f"Control n={control_n}, "
                        f"Treatment n={treatment_n}, "
                        f"Effect=+{effect_pp} pp"
                    )

                    result = simulate_scenario(
                        baseline_rate=baseline,
                        treatment_effect_pp=effect_pp,
                        control_n=control_n,
                        treatment_n=treatment_n,
                        rng=rng,
                    )

                    if effect_pp == 0:
                        nominal_se_pp = (
                            np.sqrt(
                                ALPHA * (1 - ALPHA)
                                / SIMULATIONS
                            )
                            * 100
                        )

                        tolerance_pp = 3 * nominal_se_pp

                        assessment = (
                            "PASS"
                            if abs(
                                result["empirical_rate_pct"]
                                - ALPHA * 100
                            ) <= tolerance_pp
                            else "REVIEW"
                        )
                    else:
                        assessment = "MEASURED"

                    records.append({
                        "baseline_conversion_pct": baseline * 100,
                        "allocation_ratio": allocation_ratio,
                        "control_sample_size": control_n,
                        "treatment_sample_size": treatment_n,
                        "treatment_effect_pp": effect_pp,
                        "analysis_type": analysis_type,
                        "simulations": SIMULATIONS,
                        "significant_count": result[
                            "significant_count"
                        ],
                        "empirical_rate_pct": result[
                            "empirical_rate_pct"
                        ],
                        "monte_carlo_se_pp": result[
                            "monte_carlo_se_pp"
                        ],
                        "nominal_alpha_pct": ALPHA * 100,
                        "assessment": assessment,
                    })

    report = pd.DataFrame(records)

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    report.to_csv(OUTPUT_PATH, index=False)

    print("\nSENSITIVITY AND ALLOCATION ROBUSTNESS")
    print("=" * 90)

    print(f"Random seed: {SEED}")
    print(f"Simulations per scenario: {SIMULATIONS:,}")
    print(f"Total scenarios: {len(report):,}")
    print(
        f"Total simulation runs: "
        f"{len(report) * SIMULATIONS:,}"
    )

    print("\nTYPE I ERROR VALIDATION")
    print("-" * 90)

    type_i = report[
        report["analysis_type"] == "TYPE_I_ERROR"
    ]

    print(
        type_i[
            [
                "baseline_conversion_pct",
                "allocation_ratio",
                "control_sample_size",
                "treatment_sample_size",
                "empirical_rate_pct",
                "monte_carlo_se_pp",
                "assessment",
            ]
        ].to_string(index=False)
    )

    print("\nSTATISTICAL POWER SUMMARY")
    print("-" * 90)

    power = report[
        report["analysis_type"] == "STATISTICAL_POWER"
    ]

    summary = (
        power.groupby(
            [
                "allocation_ratio",
                "treatment_effect_pp",
            ]
        )["empirical_rate_pct"]
        .mean()
        .reset_index()
    )

    print(summary.to_string(index=False))

    print("\nASSESSMENT SUMMARY")
    print("-" * 90)
    print(report["assessment"].value_counts().to_string())

    review_count = (
        report.loc[
            report["analysis_type"] == "TYPE_I_ERROR",
            "assessment",
        ] == "REVIEW"
    ).sum()

    overall = "PASS" if review_count == 0 else "REVIEW"

    print(f"\nOVERALL ASSESSMENT: {overall}")
    print(f"\nSaved report: {OUTPUT_PATH}")


if __name__ == "__main__":
    run_sensitivity_validation()

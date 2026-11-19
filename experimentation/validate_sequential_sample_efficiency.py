
import csv
from pathlib import Path

import numpy as np

from experimentation.analyze_event_experiments import compare_variants

# ============================================================
# SEQUENTIAL MONITORING: SAMPLE EFFICIENCY VALIDATION
# ============================================================

SEED = 20261125
SIMULATIONS = 20000
ALPHA = 0.05

FINAL_SAMPLE_SIZE_PER_VARIANT = 2000
INTERIM_LOOKS = [500, 1000, 1500, 2000]

BASELINES = [0.05, 0.10, 0.20, 0.40, 0.60]
TREATMENT_EFFECTS = [0.02, 0.04, 0.06]

OUTPUT_PATH = Path(
    "data/synthetic/experiment_dataset/"
    "sequential_sample_efficiency_validation.csv"
)

rng = np.random.default_rng(SEED)


def simulate_experiment(baseline, treatment_effect):
    """Generate cumulative Bernoulli observations."""

    treatment_rate = baseline + treatment_effect

    if treatment_rate >= 1:
        raise ValueError(
            "Treatment conversion rate must be below 100%."
        )

    control = rng.binomial(
        1,
        baseline,
        FINAL_SAMPLE_SIZE_PER_VARIANT,
    )

    treatment = rng.binomial(
        1,
        treatment_rate,
        FINAL_SAMPLE_SIZE_PER_VARIANT,
    )

    return control, treatment


def evaluate_scenario(baseline, treatment_effect):
    corrected_alpha = ALPHA / len(INTERIM_LOOKS)

    methods = [
        "FIXED_HORIZON",
        "NAIVE_REPEATED",
        "BONFERRONI_REPEATED",
    ]

    results = {
        method: {
            "detections": 0,
            "look_counts": {
                look: 0 for look in INTERIM_LOOKS
            },
            "total_sample_size": 0,
            "maximum_sample_runs": 0,
        }
        for method in methods
    }

    for _ in range(SIMULATIONS):
        control, treatment = simulate_experiment(
            baseline,
            treatment_effect,
        )

        naive_detection = None
        corrected_detection = None
        fixed_detection = None

        for sample_size in INTERIM_LOOKS:
            control_x = int(control[:sample_size].sum())
            treatment_x = int(treatment[:sample_size].sum())

            analysis = compare_variants(
                sample_size,
                control_x,
                sample_size,
                treatment_x,
                ALPHA,
            )

            p_value = analysis["p_value"]

            if (
                naive_detection is None
                and p_value < ALPHA
            ):
                naive_detection = sample_size

            if (
                corrected_detection is None
                and p_value < corrected_alpha
            ):
                corrected_detection = sample_size

            if sample_size == FINAL_SAMPLE_SIZE_PER_VARIANT:
                if analysis["statistically_significant"]:
                    fixed_detection = sample_size

        detections = {
            "FIXED_HORIZON": fixed_detection,
            "NAIVE_REPEATED": naive_detection,
            "BONFERRONI_REPEATED": corrected_detection,
        }

        for method, detection in detections.items():
            result = results[method]

            if detection is not None:
                result["detections"] += 1
                result["look_counts"][detection] += 1

                actual_sample_size = detection
            else:
                actual_sample_size = (
                    FINAL_SAMPLE_SIZE_PER_VARIANT
                )

            result["total_sample_size"] += (
                actual_sample_size * 2
            )

            if (
                actual_sample_size
                == FINAL_SAMPLE_SIZE_PER_VARIANT
            ):
                result["maximum_sample_runs"] += 1

    rows = []

    fixed_expected_sample_size = (
        FINAL_SAMPLE_SIZE_PER_VARIANT * 2
    )

    for method in methods:
        result = results[method]

        detections = result["detections"]
        power = detections / SIMULATIONS

        expected_sample_size = (
            result["total_sample_size"] / SIMULATIONS
        )

        sample_size_savings_pct = (
            (
                fixed_expected_sample_size
                - expected_sample_size
            )
            / fixed_expected_sample_size
            * 100
        )

        maximum_sample_pct = (
            result["maximum_sample_runs"]
            / SIMULATIONS
            * 100
        )

        look_distribution = {
            look: (
                result["look_counts"][look]
                / SIMULATIONS
                * 100
            )
            for look in INTERIM_LOOKS
        }

        monte_carlo_se = (
            (power * (1 - power) / SIMULATIONS) ** 0.5
        )

        rows.append({
            "baseline_conversion_pct": baseline * 100,
            "treatment_effect_pp": treatment_effect * 100,
            "treatment_conversion_pct": (
                baseline + treatment_effect
            ) * 100,
            "method": method,
            "simulations": SIMULATIONS,
            "detections": detections,
            "empirical_power_pct": power * 100,
            "no_detection_pct": (1 - power) * 100,
            "detection_at_500_pct": look_distribution[500],
            "detection_at_1000_pct": look_distribution[1000],
            "detection_at_1500_pct": look_distribution[1500],
            "detection_at_2000_pct": look_distribution[2000],
            "expected_sample_size_total": expected_sample_size,
            "expected_sample_size_per_variant": (
                expected_sample_size / 2
            ),
            "sample_size_savings_pct": sample_size_savings_pct,
            "maximum_sample_size_runs_pct": maximum_sample_pct,
            "monte_carlo_se_pp": monte_carlo_se * 100,
            "final_sample_size_per_variant": (
                FINAL_SAMPLE_SIZE_PER_VARIANT
            ),
            "nominal_alpha_pct": ALPHA * 100,
            "corrected_alpha_pct": (
                corrected_alpha * 100
                if method == "BONFERRONI_REPEATED"
                else ""
            ),
            "seed": SEED,
        })

    return rows


def main():
    all_rows = []

    print("=" * 105)
    print("SEQUENTIAL MONITORING: SAMPLE EFFICIENCY VALIDATION")
    print("=" * 105)
    print(f"Random seed: {SEED}")
    print(f"Simulations per scenario: {SIMULATIONS:,}")
    print(f"Final sample size per variant: {FINAL_SAMPLE_SIZE_PER_VARIANT}")
    print(f"Interim looks: {INTERIM_LOOKS}")
    print(f"Baselines: {BASELINES}")
    print(f"Treatment effects: {TREATMENT_EFFECTS}")
    print(f"Nominal alpha: {ALPHA}")
    print()

    for baseline in BASELINES:
        for effect in TREATMENT_EFFECTS:
            print(
                f"Baseline: {baseline:.0%} | "
                f"Treatment effect: +{effect * 100:.0f} pp"
            )

            rows = evaluate_scenario(baseline, effect)
            all_rows.extend(rows)

            for row in rows:
                print(
                    f"  {row['method']:<22} "
                    f"Power: {row['empirical_power_pct']:>6.2f}% | "
                    f"Expected total n: "
                    f"{row['expected_sample_size_total']:>7.1f} | "
                    f"Sample savings: "
                    f"{row['sample_size_savings_pct']:>6.2f}% | "
                    f"No detection: "
                    f"{row['no_detection_pct']:>6.2f}%"
                )

            print()

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with OUTPUT_PATH.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=list(all_rows[0].keys()),
        )
        writer.writeheader()
        writer.writerows(all_rows)

    print("=" * 105)
    print("VALIDATION SUMMARY")
    print("=" * 105)
    print(f"Total report rows: {len(all_rows)}")
    print(
        f"Simulated experiments: "
        f"{SIMULATIONS * len(BASELINES) * len(TREATMENT_EFFECTS):,}"
    )
    print("Methods compared: 3")
    print(f"Output: {OUTPUT_PATH}")
    print()
    print("RESULT: SAMPLE EFFICIENCY SIMULATION COMPLETED")
    print(
        "Expected sample size includes experiments that "
        "reach the final look without detection."
    )


if __name__ == "__main__":
    main()

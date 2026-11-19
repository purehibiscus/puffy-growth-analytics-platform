
import csv
import math
from pathlib import Path

import numpy as np
from scipy.stats import norm

# ============================================================
# SEQUENTIAL MONITORING AND OPTIONAL STOPPING VALIDATION
# ============================================================

SEED = 20261123
SIMULATIONS = 20000
ALPHA = 0.05

FINAL_SAMPLE_SIZE_PER_VARIANT = 2000
INTERIM_LOOKS = [500, 1000, 1500, 2000]

BASELINES = [0.05, 0.10, 0.20, 0.40, 0.60]

OUTPUT_PATH = Path(
    "data/synthetic/experiment_dataset/"
    "sequential_monitoring_validation.csv"
)

rng = np.random.default_rng(SEED)


def pooled_two_proportion_p_value(
    control_n,
    control_x,
    treatment_n,
    treatment_x,
):
    """Calculate a two-sided pooled two-proportion z-test p-value."""

    pooled_rate = (
        control_x + treatment_x
    ) / (
        control_n + treatment_n
    )

    standard_error = math.sqrt(
        pooled_rate
        * (1 - pooled_rate)
        * (1 / control_n + 1 / treatment_n)
    )

    if standard_error == 0:
        return 1.0

    control_rate = control_x / control_n
    treatment_rate = treatment_x / treatment_n

    z_score = (
        treatment_rate - control_rate
    ) / standard_error

    return float(2 * norm.sf(abs(z_score)))


def simulate_null_experiment(baseline):
    """Simulate cumulative observations under equal conversion rates."""

    control_data = rng.binomial(
        1,
        baseline,
        FINAL_SAMPLE_SIZE_PER_VARIANT,
    )

    treatment_data = rng.binomial(
        1,
        baseline,
        FINAL_SAMPLE_SIZE_PER_VARIANT,
    )

    return control_data, treatment_data


def evaluate_scenario(baseline):
    naive_false_positives = 0
    corrected_false_positives = 0
    fixed_false_positives = 0

    looks = len(INTERIM_LOOKS)
    corrected_alpha = ALPHA / looks

    for _ in range(SIMULATIONS):
        control, treatment = simulate_null_experiment(baseline)

        naive_significant = False
        corrected_significant = False

        for sample_size in INTERIM_LOOKS:
            control_x = int(control[:sample_size].sum())
            treatment_x = int(treatment[:sample_size].sum())

            p_value = pooled_two_proportion_p_value(
                sample_size,
                control_x,
                sample_size,
                treatment_x,
            )

            if p_value < ALPHA:
                naive_significant = True

            if p_value < corrected_alpha:
                corrected_significant = True

        final_control_x = int(
            control[:FINAL_SAMPLE_SIZE_PER_VARIANT].sum()
        )
        final_treatment_x = int(
            treatment[:FINAL_SAMPLE_SIZE_PER_VARIANT].sum()
        )

        final_p_value = pooled_two_proportion_p_value(
            FINAL_SAMPLE_SIZE_PER_VARIANT,
            final_control_x,
            FINAL_SAMPLE_SIZE_PER_VARIANT,
            final_treatment_x,
        )

        if final_p_value < ALPHA:
            fixed_false_positives += 1

        if naive_significant:
            naive_false_positives += 1

        if corrected_significant:
            corrected_false_positives += 1

    methods = {
        "FIXED_HORIZON": fixed_false_positives,
        "NAIVE_REPEATED": naive_false_positives,
        "BONFERRONI_REPEATED": corrected_false_positives,
    }

    rows = []

    for method, false_positives in methods.items():
        rate = false_positives / SIMULATIONS

        monte_carlo_se = math.sqrt(
            rate * (1 - rate) / SIMULATIONS
        )

        upper_screening_limit = (
            ALPHA + 3 * math.sqrt(
                ALPHA * (1 - ALPHA) / SIMULATIONS
            )
        )

        if method == "NAIVE_REPEATED":
            assessment = "DIAGNOSTIC"
        else:
            assessment = (
                "PASS"
                if rate <= upper_screening_limit
                else "REVIEW"
            )

        rows.append({
            "baseline_conversion_pct": baseline * 100,
            "method": method,
            "simulations": SIMULATIONS,
            "false_positives": false_positives,
            "empirical_type_i_error_pct": rate * 100,
            "monte_carlo_se_pp": monte_carlo_se * 100,
            "nominal_alpha_pct": ALPHA * 100,
            "planned_interim_looks": looks,
            "corrected_alpha_pct": (
                corrected_alpha * 100
                if method == "BONFERRONI_REPEATED"
                else ""
            ),
            "assessment": assessment,
            "seed": SEED,
        })

    return rows


def main():
    all_rows = []

    print("=" * 90)
    print("SEQUENTIAL MONITORING AND OPTIONAL STOPPING VALIDATION")
    print("=" * 90)
    print(f"Random seed: {SEED}")
    print(f"Simulations per baseline: {SIMULATIONS:,}")
    print(f"Final sample size per variant: {FINAL_SAMPLE_SIZE_PER_VARIANT}")
    print(f"Interim looks: {INTERIM_LOOKS}")
    print(f"Nominal alpha: {ALPHA}")
    print()

    for baseline in BASELINES:
        print(f"Baseline conversion: {baseline:.0%}")

        rows = evaluate_scenario(baseline)
        all_rows.extend(rows)

        for row in rows:
            print(
                f"  {row['method']:<22} "
                f"Type I error: "
                f"{row['empirical_type_i_error_pct']:.2f}% "
                f"| {row['assessment']}"
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

    review_rows = [
        row for row in all_rows
        if row["method"] != "NAIVE_REPEATED"
        and row["assessment"] != "PASS"
    ]

    print("=" * 90)
    print("VALIDATION SUMMARY")
    print("=" * 90)
    print(f"Total report rows: {len(all_rows)}")
    print(f"Simulated experiments: {SIMULATIONS * len(BASELINES):,}")
    print(f"Methods compared: 3")
    print(f"Rows requiring review: {len(review_rows)}")
    print(f"Output: {OUTPUT_PATH}")

    if review_rows:
        print("\nRESULT: REVIEW REQUIRED")
        raise SystemExit(1)

    print("\nRESULT: FALSE-POSITIVE SCREENING PASSED")
    print(
        "Bonferroni is a conservative correction; "
        "this validation does not establish optimal sequential design."
    )


if __name__ == "__main__":
    main()

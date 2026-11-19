
import csv
import math
from pathlib import Path

import numpy as np

from analyze_event_experiments import compare_variants


# ============================================================
# FIXED-TOTAL-SAMPLE ALLOCATION ROBUSTNESS VALIDATION
# ============================================================

SEED = 20261122
SIMULATIONS = 5000
ALPHA = 0.05
TOTAL_SAMPLE_SIZE = 2400
TARGET_POWER = 0.80

BASELINES = [0.05, 0.10, 0.20, 0.40, 0.60]
EFFECTS_PP = [0, 2, 4, 6]

ALLOCATIONS = {
    "1:1": (1200, 1200),
    "1:1.5": (960, 1440),
    "1:2": (800, 1600),
}

OUTPUT_PATH = Path(
    "data/synthetic/experiment_dataset/"
    "fixed_total_allocation_validation.csv"
)

rng = np.random.default_rng(SEED)


def empirical_power(
    baseline,
    effect,
    control_n,
    treatment_n,
):
    treatment_rate = baseline + effect

    if treatment_rate > 1:
        raise ValueError("Treatment conversion rate cannot exceed 100%.")

    significant = 0

    for _ in range(SIMULATIONS):
        control_x = rng.binomial(control_n, baseline)
        treatment_x = rng.binomial(treatment_n, treatment_rate)

        result = compare_variants(
            control_n=control_n,
            control_x=int(control_x),
            treatment_n=treatment_n,
            treatment_x=int(treatment_x),
            alpha=ALPHA,
        )

        if result["statistically_significant"]:
            significant += 1

    power = significant / SIMULATIONS
    monte_carlo_se = math.sqrt(
        power * (1 - power) / SIMULATIONS
    )

    return power, monte_carlo_se


def main():
    rows = []

    print("=" * 90)
    print("FIXED-TOTAL-SAMPLE ALLOCATION VALIDATION")
    print("=" * 90)
    print(f"Random seed: {SEED}")
    print(f"Simulations per scenario: {SIMULATIONS:,}")
    print(f"Total sample size per scenario: {TOTAL_SAMPLE_SIZE:,}")
    print(f"Alpha: {ALPHA}")
    print(f"Target power reference: {TARGET_POWER:.0%}")
    print()

    for allocation, (control_n, treatment_n) in ALLOCATIONS.items():

        assert control_n + treatment_n == TOTAL_SAMPLE_SIZE

        print(
            f"Allocation {allocation}: "
            f"Control={control_n}, Treatment={treatment_n}"
        )

        for baseline in BASELINES:
            for effect_pp in EFFECTS_PP:

                effect = effect_pp / 100

                power, monte_carlo_se = empirical_power(
                    baseline=baseline,
                    effect=effect,
                    control_n=control_n,
                    treatment_n=treatment_n,
                )

                if effect_pp == 0:
                    assessment = (
                        "PASS"
                        if power <= ALPHA + 3 * monte_carlo_se
                        else "REVIEW"
                    )
                    analysis_type = "TYPE_I_ERROR"
                else:
                    assessment = "MEASURED"
                    analysis_type = "POWER"

                row = {
                    "allocation_ratio": allocation,
                    "control_sample_size": control_n,
                    "treatment_sample_size": treatment_n,
                    "total_sample_size": TOTAL_SAMPLE_SIZE,
                    "baseline_conversion_pct": round(
                        baseline * 100, 4
                    ),
                    "treatment_effect_pp": effect_pp,
                    "analysis_type": analysis_type,
                    "empirical_power_pct": round(
                        power * 100, 4
                    ),
                    "monte_carlo_se_pp": round(
                        monte_carlo_se * 100, 4
                    ),
                    "assessment": assessment,
                    "simulations": SIMULATIONS,
                    "alpha": ALPHA,
                    "seed": SEED,
                }

                rows.append(row)

                print(
                    f"  Baseline={baseline:.0%}, "
                    f"Effect=+{effect_pp}pp, "
                    f"Power={power:.2%}, "
                    f"Assessment={assessment}"
                )

        print()

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = list(rows[0].keys())

    with OUTPUT_PATH.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=fieldnames,
        )
        writer.writeheader()
        writer.writerows(rows)

    type_i_error_rows = [
        row for row in rows
        if row["analysis_type"] == "TYPE_I_ERROR"
    ]

    failed = [
        row for row in type_i_error_rows
        if row["assessment"] != "PASS"
    ]

    print("=" * 90)
    print("VALIDATION SUMMARY")
    print("=" * 90)
    print(f"Total scenarios: {len(rows)}")
    print(f"Type I error scenarios: {len(type_i_error_rows)}")
    print(f"Type I error failures: {len(failed)}")
    print(f"Output: {OUTPUT_PATH}")

    if failed:
        print("\nRESULT: REVIEW REQUIRED")
        raise SystemExit(1)

    print("\nRESULT: TYPE I ERROR VALIDATION PASSED")
    print(
        "Power results are measurements, not pass/fail guarantees."
    )


if __name__ == "__main__":
    main()

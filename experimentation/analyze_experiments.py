from pathlib import Path
import math

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "synthetic"

EXPERIMENTS_FILE = DATA_DIR / "experiments.csv"
ASSIGNMENTS_FILE = DATA_DIR / "experiment_assignments.csv"


def load_experiment_data():
    """Load experiment definitions and assignments without modifying source files."""
    experiments = pd.read_csv(EXPERIMENTS_FILE)
    assignments = pd.read_csv(ASSIGNMENTS_FILE)

    required_experiment_columns = {
        "experiment_id",
        "primary_kpi",
        "start_date",
        "end_date",
        "status",
    }
    required_assignment_columns = {
        "assignment_id",
        "experiment_id",
        "user_id",
        "assignment_timestamp",
        "variant",
        "eligible",
        "converted",
        "revenue",
        "checkout_completed",
        "guardrail_refund",
    }

    missing_experiment_columns = required_experiment_columns - set(
        experiments.columns
    )
    missing_assignment_columns = required_assignment_columns - set(
        assignments.columns
    )

    if missing_experiment_columns:
        raise ValueError(
            f"Missing experiment columns: {sorted(missing_experiment_columns)}"
        )

    if missing_assignment_columns:
        raise ValueError(
            f"Missing assignment columns: {sorted(missing_assignment_columns)}"
        )


    # Validate registry identifiers before using them to join assignment data.
    for column in ["experiment_id", "start_date", "end_date", "primary_kpi", "status"]:
        if experiments[column].isna().any() or experiments[column].astype("string").str.strip().eq("").any():
            raise ValueError(f"Experiment registry contains blank values in {column!r}")

    if experiments["experiment_id"].duplicated().any():
        raise ValueError("Duplicate experiment IDs detected in registry")

    # Required identifiers must be present and nonblank.
    for column in ["assignment_id", "experiment_id", "user_id", "variant"]:
        if assignments[column].isna().any() or assignments[column].astype("string").str.strip().eq("").any():
            raise ValueError(f"Assignments contain blank values in {column!r}")

    if assignments["assignment_id"].duplicated().any():
        raise ValueError("Duplicate assignment IDs detected")

    known_experiments = set(experiments["experiment_id"])
    unknown_experiments = set(assignments["experiment_id"]) - known_experiments
    if unknown_experiments:
        raise ValueError(
            f"Assignments reference unknown experiment IDs: {sorted(unknown_experiments)}"
        )

    # Normalize variants, but reject unexpected labels.
    assignments["variant"] = (
        assignments["variant"].astype("string").str.strip().str.lower()
    )
    invalid_variants = ~assignments["variant"].isin(["control", "treatment"])
    if invalid_variants.any():
        values = assignments.loc[invalid_variants, "variant"].unique().tolist()
        raise ValueError(f"Invalid variant values: {values}")

    # Parse timestamps strictly: never silently drop malformed dates.
    raw_timestamps = assignments["assignment_timestamp"].copy()
    assignments["assignment_timestamp"] = pd.to_datetime(
        raw_timestamps, errors="coerce"
    )
    if assignments["assignment_timestamp"].isna().any():
        count = int(assignments["assignment_timestamp"].isna().sum())
        raise ValueError(f"Invalid or missing assignment timestamps: {count}")

    # Accept common boolean representations, rejecting anything else.
    assignments["eligible"] = (
        assignments["eligible"]
        .astype("string")
        .str.strip()
        .str.lower()
        .map({"true": True, "false": False})
    )
    if assignments["eligible"].isna().any():
        count = int(assignments["eligible"].isna().sum())
        raise ValueError(f"Invalid or missing eligibility values: {count}")

    # Convert numeric fields, then validate their values and ranges.
    numeric_columns = [
        "converted",
        "revenue",
        "checkout_completed",
        "guardrail_refund",
    ]
    for column in numeric_columns:
        assignments[column] = pd.to_numeric(assignments[column], errors="coerce")
        if assignments[column].isna().any():
            count = int(assignments[column].isna().sum())
            raise ValueError(f"Invalid or missing numeric values in {column!r}: {count}")

    binary_columns = ["converted", "checkout_completed", "guardrail_refund"]
    for column in binary_columns:
        invalid = ~assignments[column].isin([0, 1])
        if invalid.any():
            raise ValueError(f"Non-binary values detected in {column!r}")

    if not assignments["revenue"].map(math.isfinite).all():
        raise ValueError("Revenue contains non-finite values")

    if assignments["revenue"].lt(0).any():
        raise ValueError("Negative revenue values detected")

    # Validate the experiment registry's dates and statistical parameters.
    starts = pd.to_datetime(experiments["start_date"], errors="coerce")
    ends = pd.to_datetime(experiments["end_date"], errors="coerce")
    if starts.isna().any() or ends.isna().any() or starts.gt(ends).any():
        raise ValueError("Invalid experiment registry date range")

    for column in ["alpha", "power"]:
        if column not in experiments.columns:
            continue
        values = pd.to_numeric(experiments[column], errors="coerce")
        if values.isna().any() or not values.between(0, 1, inclusive="neither").all():
            raise ValueError(f"Invalid experiment parameter in {column!r}")

    return experiments, assignments



def analyze_experiment(experiment, assignments):
    """Summarize one experiment and flag assignment-integrity limitations."""
    experiment_id = experiment["experiment_id"]
    start = pd.Timestamp(experiment["start_date"])
    end_exclusive = pd.Timestamp(experiment["end_date"]) + pd.Timedelta(days=1)

    experiment_rows = assignments[
        assignments["experiment_id"] == experiment_id
    ].copy()

    in_window = experiment_rows[
        experiment_rows["assignment_timestamp"].ge(start)
        & experiment_rows["assignment_timestamp"].lt(end_exclusive)
    ].copy()

    eligible = in_window[in_window["eligible"].eq(True)].copy()

    issues = []

    out_of_window_count = len(experiment_rows) - len(in_window)
    ineligible_count = int(in_window["eligible"].eq(False).sum())

    if out_of_window_count:
        issues.append(f"{out_of_window_count} assignment(s) outside experiment window")

    if ineligible_count:
        issues.append(f"{ineligible_count} ineligible assignment(s) inside window")

    if experiment_rows["assignment_id"].duplicated().any():
        issues.append("Duplicate assignment IDs detected")

    duplicate_users = int(
        eligible.duplicated(["experiment_id", "user_id"], keep=False).sum()
    )
    if duplicate_users:
        issues.append(
            f"{duplicate_users} eligible assignment rows belong to repeated users"
        )

    variant_counts_per_user = eligible.groupby("user_id")["variant"].nunique()
    cross_variant_users = int((variant_counts_per_user > 1).sum())

    if cross_variant_users:
        issues.append(
            f"{cross_variant_users} eligible user(s) appear in multiple variants"
        )

    results = []

    for variant in ["control", "treatment"]:
        group = eligible[
            eligible["variant"].astype("string").str.lower() == variant
        ].copy()

        n = len(group)
        converted = int(group["converted"].sum()) if n else 0
        converted_flag_rate = converted / n if n else float("nan")
        revenue_per_assignment = (
            group["revenue"].sum() / n if n else float("nan")
        )
        checkout_rate = (
            group["checkout_completed"].mean() if n else float("nan")
        )
        refund_rate = (
            group["guardrail_refund"].mean() if n else float("nan")
        )

        results.append({
            "experiment_id": experiment_id,
            "variant": variant,
            "eligible_assignments": n,
            "unique_users": group["user_id"].nunique(),
            "conversions": converted,
            "converted_flag_rate": converted_flag_rate,
            "revenue_per_assignment": revenue_per_assignment,
            "checkout_completion_rate": checkout_rate,
            "refund_guardrail_rate": refund_rate,
        })

    summary = pd.DataFrame(results)

    control = summary[summary["variant"] == "control"].iloc[0]
    treatment = summary[summary["variant"] == "treatment"].iloc[0]

    p_control = control["converted_flag_rate"]
    p_treatment = treatment["converted_flag_rate"]
    n_control = control["eligible_assignments"]
    n_treatment = treatment["eligible_assignments"]

    difference = p_treatment - p_control

    if n_control and n_treatment and not duplicate_users and not cross_variant_users and not (
        math.isnan(p_control) or math.isnan(p_treatment)
    ):
        standard_error = math.sqrt(
            p_control * (1 - p_control) / n_control
            + p_treatment * (1 - p_treatment) / n_treatment
        )
        ci_low = difference - 1.96 * standard_error
        ci_high = difference + 1.96 * standard_error
    else:
        ci_low = float("nan")
        ci_high = float("nan")

    summary["converted_flag_absolute_difference"] = difference
    summary["conversion_ci95_low"] = ci_low
    summary["conversion_ci95_high"] = ci_high
    summary["experiment_status"] = experiment["status"]
    summary["primary_kpi"] = experiment["primary_kpi"]
    summary["assignment_integrity_warning"] = "; ".join(issues) if issues else "None detected"

    if cross_variant_users or duplicate_users:
        summary["statistical_interpretation"] = (
            "CAUTION: repeated or cross-variant users may invalidate "
            "ordinary independent-assignment confidence intervals"
        )
    else:
        summary["statistical_interpretation"] = (
            "Approximate interval; review experiment design and metric definitions"
        )

    if str(experiment["status"]).strip().lower() != "completed":
        summary["result_maturity"] = "INTERIM — experiment not marked completed"
    else:
        summary["result_maturity"] = "Completed status — still review data quality"

    return summary


def run_analysis():
    """Run the experiment summaries and print results to the terminal."""
    experiments, assignments = load_experiment_data()
    all_results = []

    for _, experiment in experiments.iterrows():
        result = analyze_experiment(experiment, assignments)
        all_results.append(result)

    if not all_results:
        print("No experiments found.")
        return

    report = pd.concat(all_results, ignore_index=True)

    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 220)

    print("\nEXPERIMENT ANALYSIS")
    print("===================")
    print(report.to_string(index=False))

    print("\nInterpretation notes:")
    print("- Source CSVs are read-only; this script does not write reports.")
    print("- converted_flag_rate is an exploratory proxy, not a validated primary KPI.")
    print("- Primary KPI definitions and denominators are not documented in the source data.")
    print("- Do not declare a winning variant until assignment integrity and KPI definitions are resolved.")
    print("- Confidence intervals are withheld when repeated or cross-variant users are detected.")
    print("- No statistical significance or winning variant is declared.")
    print("- Refund guardrail rates are descriptive; confirm their intended definition.")
    print("- EXP-025 is interim while its recorded status remains running.")


if __name__ == "__main__":
    run_analysis()

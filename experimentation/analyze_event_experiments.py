
from pathlib import Path
import math

import numpy as np
import pandas as pd
from scipy.stats import chi2, norm


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data" / "synthetic"
DATASET_DIR = DATA_DIR / "experiment_dataset"

REGISTRY_PATH = DATA_DIR / "experiments.csv"
ASSIGNMENTS_PATH = DATASET_DIR / "experiment_assignments.csv"
EVENTS_PATH = DATASET_DIR / "ga4_experiment_events.csv"

SUMMARY_OUTPUT = DATASET_DIR / "event_experiment_analysis.csv"
INTEGRITY_OUTPUT = DATASET_DIR / "event_experiment_integrity.csv"


def require_columns(df, columns, name):
    missing = sorted(set(columns) - set(df.columns))
    if missing:
        raise ValueError(f"{name} is missing columns: {missing}")


def as_bool(series):
    """Parse CSV boolean values without treating non-empty strings as True."""
    return (
        series.astype(str)
        .str.strip()
        .str.lower()
        .map({"true": True, "false": False, "1": True, "0": False})
    )


def in_window(series, start, end):
    """Use an inclusive calendar end date, represented as an exclusive bound."""
    return (series >= start) & (series < end + pd.Timedelta(days=1))

def reconcile_denominator(eligible_assignments, denominator_users):
    """Reconcile eligible assigned users against denominator-qualified users."""
    assigned_users = set(eligible_assignments["user_id"].dropna())
    denominator_users = set(denominator_users)

    qualified_users = assigned_users.intersection(denominator_users)
    missing_denominator_users = assigned_users.difference(qualified_users)

    return {
        "eligible_assigned_users": len(assigned_users),
        "denominator_users": len(qualified_users),
        "eligible_users_without_denominator_event": len(
            missing_denominator_users
        ),
        "denominator_reconciles": (
            len(assigned_users)
            == len(qualified_users) + len(missing_denominator_users)
        ),
    }

def first_event_per_user(events, event_name):
    selected = events.loc[events["event_name"].eq(event_name)].copy()
    return selected.sort_values("event_timestamp").drop_duplicates("user_id")


def calculate_kpi(experiment_id, eligible_assignments, events):
    """
    Return user-level denominator/numerator counts for the registered KPI.

    EXP-024: view_item -> later add_to_cart, same session and product where
    product IDs are populated.

    EXP-025: begin_checkout -> later purchase, same session, mobile only.
    """
    exp_events = events.loc[
        events["experiment_id"].eq(experiment_id)
    ].copy()

    exp_events = exp_events.sort_values("event_timestamp")

    if experiment_id == "EXP-024":
        denominator_event = "view_item"
        numerator_event = "add_to_cart"
    elif experiment_id == "EXP-025":
        denominator_event = "begin_checkout"
        numerator_event = "purchase"
        eligible_assignments = eligible_assignments.loc[
            eligible_assignments["device_category"].eq("mobile")
        ].copy()
        exp_events = exp_events.loc[
            exp_events["device_category"].eq("mobile")
        ].copy()
    else:
        raise ValueError(f"No event-level KPI definition for {experiment_id}")

    assigned_users = set(eligible_assignments["user_id"].dropna())

    # Denominator: eligible assigned users with the denominator event.
    denominator_events = exp_events.loc[
        exp_events["event_name"].eq(denominator_event)
        & exp_events["user_id"].isin(assigned_users)
    ].copy()

    denominator_events = denominator_events.drop_duplicates(
        ["user_id", "session_id"]
    )

    denominator_users = set(denominator_events["user_id"])

    # Numerator: denominator users with a later qualifying event in the
    # same session. For EXP-024, product IDs must match when both are present.
    numerator_users = set()

    for row in denominator_events.itertuples(index=False):
        later = exp_events.loc[
            exp_events["user_id"].eq(row.user_id)
            & exp_events["session_id"].eq(row.session_id)
            & exp_events["event_name"].eq(numerator_event)
            & (exp_events["event_timestamp"] > row.event_timestamp)
        ]

        if experiment_id == "EXP-024":
            if pd.notna(row.product_id):
                later = later.loc[
                    later["product_id"].isna()
                    | later["product_id"].eq(row.product_id)
                ]

        if not later.empty:
            numerator_users.add(row.user_id)

    # A user is counted once even if they have multiple qualifying sessions.
    denominator_users = denominator_users.intersection(assigned_users)
    numerator_users = numerator_users.intersection(denominator_users)

    return denominator_event, numerator_event, denominator_users, numerator_users


def compare_variants(control_n, control_x, treatment_n, treatment_x, alpha):
    """Two-sided pooled two-proportion z-test and Wald CI for rate difference."""
    if min(control_n, treatment_n) <= 0:
        return {
            "absolute_lift_pp": np.nan,
            "relative_lift_pct": np.nan,
            "confidence_interval_low_pp": np.nan,
            "confidence_interval_high_pp": np.nan,
            "p_value": np.nan,
            "statistically_significant": False,
        }

    p_control = control_x / control_n
    p_treatment = treatment_x / treatment_n
    difference = p_treatment - p_control

    pooled = (control_x + treatment_x) / (control_n + treatment_n)
    se_test = math.sqrt(
        pooled * (1 - pooled) * (1 / control_n + 1 / treatment_n)
    ) if 0 < pooled < 1 else 0.0

    if se_test > 0:
        z_score = difference / se_test
        p_value = float(2 * norm.sf(abs(z_score)))
    else:
        p_value = 1.0 if difference == 0 else 0.0

    se_ci = math.sqrt(
        p_control * (1 - p_control) / control_n
        + p_treatment * (1 - p_treatment) / treatment_n
    )
    z_critical = norm.ppf(1 - alpha / 2)

    relative_lift = (
        (p_treatment / p_control - 1) * 100
        if p_control > 0
        else np.nan
    )

    return {
        "absolute_lift_pp": difference * 100,
        "relative_lift_pct": relative_lift,
        "confidence_interval_low_pp": (difference - z_critical * se_ci) * 100,
        "confidence_interval_high_pp": (difference + z_critical * se_ci) * 100,
        "p_value": p_value,
        "statistically_significant": bool(p_value < alpha),
    }



def check_sample_ratio_mismatch(
    control_n,
    treatment_n,
    expected_control_share=0.5,
    alpha=0.001,
):
    """Test assigned-user counts against the expected allocation using chi-square."""
    if control_n < 0 or treatment_n < 0:
        raise ValueError("Variant counts cannot be negative.")

    if control_n + treatment_n == 0:
        raise ValueError("At least one assigned user is required.")

    if not 0 < expected_control_share < 1:
        raise ValueError("Expected control share must be between 0 and 1.")

    if not 0 < alpha < 1:
        raise ValueError("SRM alpha must be between 0 and 1.")

    total = control_n + treatment_n
    expected_control = total * expected_control_share
    expected_treatment = total * (1 - expected_control_share)

    statistic = (
        (control_n - expected_control) ** 2 / expected_control
        + (treatment_n - expected_treatment) ** 2 / expected_treatment
    )
    p_value = float(chi2.sf(statistic, df=1))

    return {
        "control_assigned": control_n,
        "treatment_assigned": treatment_n,
        "expected_control_share": expected_control_share,
        "srm_chi_square": float(statistic),
        "srm_p_value": p_value,
        "srm_detected": bool(p_value < alpha),
        "srm_alpha": alpha,
    }


def main():
    registry = pd.read_csv(REGISTRY_PATH)
    assignments = pd.read_csv(ASSIGNMENTS_PATH)
    events = pd.read_csv(EVENTS_PATH)

    require_columns(
        registry,
        [
            "experiment_id", "experiment_name", "primary_kpi",
            "alpha", "power", "start_date", "end_date", "status",
        ],
        "Experiment registry",
    )
    require_columns(
        assignments,
        [
            "assignment_id", "experiment_id", "user_id",
            "assignment_timestamp", "variant", "device_category", "eligible",
        ],
        "Assignments",
    )
    require_columns(
        events,
        [
            "event_id", "event_timestamp", "user_id", "session_id",
            "event_name", "device_category", "product_id",
            "experiment_id", "experiment_variant",
        ],
        "Events",
    )

    assignments["assignment_timestamp"] = pd.to_datetime(
        assignments["assignment_timestamp"], utc=True, errors="coerce"
    )
    events["event_timestamp"] = pd.to_datetime(
        events["event_timestamp"], utc=True, errors="coerce"
    )
    assignments["eligible_parsed"] = as_bool(assignments["eligible"])

    integrity_rows = []
    summary_rows = []

    for exp in registry.itertuples(index=False):
        exp_id = exp.experiment_id
        start = pd.to_datetime(exp.start_date, utc=True)
        end = pd.to_datetime(exp.end_date, utc=True)
        alpha = float(exp.alpha)

        exp_assignments = assignments.loc[
            assignments["experiment_id"].eq(exp_id)
        ].copy()
        exp_events = events.loc[events["experiment_id"].eq(exp_id)].copy()

        assignment_in_window = in_window(
            exp_assignments["assignment_timestamp"], start, end
        )
        eligible_assignments = exp_assignments.loc[
            exp_assignments["eligible_parsed"].eq(True)
            & assignment_in_window
        ].copy()

        assignment_lookup = exp_assignments.drop_duplicates(
            ["experiment_id", "user_id"]
        ).set_index(["experiment_id", "user_id"])

        matched = exp_events.apply(
            lambda r: (r["experiment_id"], r["user_id"]) in assignment_lookup.index,
            axis=1,
        )
        unmatched_events = int((~matched).sum())

        comparable_events = exp_events.loc[matched].copy()
        event_variant_mismatch = 0
        event_before_assignment = 0
        event_outside_window = 0
        event_device_mismatch = 0

        for row in comparable_events.itertuples(index=False):
            key = (row.experiment_id, row.user_id)
            assignment = assignment_lookup.loc[key]

            if isinstance(assignment, pd.DataFrame):
                assignment = assignment.iloc[0]

            if str(row.experiment_variant) != str(assignment["variant"]):
                event_variant_mismatch += 1

            if row.event_timestamp < assignment["assignment_timestamp"]:
                event_before_assignment += 1

            if not (start <= row.event_timestamp < end + pd.Timedelta(days=1)):
                event_outside_window += 1

            if str(row.device_category) != str(assignment["device_category"]):
                event_device_mismatch += 1
        variant_counts = (
            exp_assignments.drop_duplicates(["experiment_id", "user_id"])
            ["variant"]
            .value_counts()
        )

        srm = check_sample_ratio_mismatch(
            control_n=int(variant_counts.get("control", 0)),
            treatment_n=int(variant_counts.get("treatment", 0)),
            expected_control_share=0.5,
            alpha=0.001,
        )

        # Exclude invalid, unmatched, pre-assignment, and out-of-window events
        # from KPI calculations. Keep original source files unchanged.
        valid_events = comparable_events.loc[
            comparable_events.apply(
                lambda r: (
                    str(r["experiment_variant"])
                    == str(assignment_lookup.loc[
                        (r["experiment_id"], r["user_id"]), "variant"
                    ])
                ),
                axis=1,
            )
        ].copy()

        valid_events = valid_events.loc[
            in_window(valid_events["event_timestamp"], start, end)
        ].copy()

        valid_events = valid_events.merge(
            exp_assignments[
                ["experiment_id", "user_id", "assignment_timestamp"]
            ].drop_duplicates(["experiment_id", "user_id"]),
            on=["experiment_id", "user_id"],
            how="inner",
        )
        valid_events = valid_events.loc[
            valid_events["event_timestamp"] >= valid_events["assignment_timestamp"]
        ].copy()

        denominator_event, numerator_event, denominator_users, numerator_users = (
            calculate_kpi(exp_id, eligible_assignments, valid_events)
        )
        reconciliation = reconcile_denominator(
            eligible_assignments, denominator_users
        )
        integrity_rows.append({
            "experiment_id": exp_id,
            "assignment_rows": len(exp_assignments),
            "eligible_assignments_in_window": len(eligible_assignments),
            "eligible_assigned_users_distinct": reconciliation["eligible_assigned_users"],
            "denominator_users_distinct": reconciliation["denominator_users"],
            "eligible_users_without_denominator_event": reconciliation["eligible_users_without_denominator_event"],
            "denominator_reconciles": reconciliation["denominator_reconciles"],
            "event_rows": len(exp_events),
            "unmatched_events": unmatched_events,
            "variant_mismatches": event_variant_mismatch,
            "events_before_assignment": event_before_assignment,
            "events_outside_window": event_outside_window,
            "device_mismatches": event_device_mismatch,
            "duplicate_assignment_ids": int(
                exp_assignments["assignment_id"].duplicated().sum()
            ),
            "duplicate_event_ids": int(exp_events["event_id"].duplicated().sum()),
            "srm_control_assigned": srm["control_assigned"],
            "srm_treatment_assigned": srm["treatment_assigned"],
            "srm_expected_control_share": srm["expected_control_share"],
            "srm_chi_square": srm["srm_chi_square"],
            "srm_p_value": srm["srm_p_value"],
            "srm_detected": srm["srm_detected"],
            "srm_alpha": srm["srm_alpha"],
        })


        for variant in ["control", "treatment"]:
            variant_assignments = eligible_assignments.loc[
                eligible_assignments["variant"].eq(variant)
            ]
            variant_users = set(variant_assignments["user_id"])

            denom = len(denominator_users.intersection(variant_users))
            numer = len(numerator_users.intersection(variant_users))
            rate = numer / denom if denom else np.nan

            summary_rows.append({
                "experiment_id": exp_id,
                "experiment_name": exp.experiment_name,
                "registry_status": exp.status,
                "primary_kpi": exp.primary_kpi,
                "variant": variant,
                "denominator_event": denominator_event,
                "numerator_event": numerator_event,
                "eligible_assigned_users": len(variant_users),
                "eligible_users_without_denominator_event": len(
                    variant_users.difference(denominator_users)
                ),
                "denominator_reconciles": (
                    len(variant_users)
                    == len(variant_users.intersection(denominator_users))
                    + len(variant_users.difference(denominator_users))
                ),
                "denominator_users": denom,
                "numerator_users": numer,
                "conversion_rate_pct": rate * 100 if denom else np.nan,
                "alpha": alpha,
                "target_power": float(exp.power),
                "interpretation": (
                    "Synthetic event-level estimate; not actual Puffy performance."
                ),
            })

        control = next(
            r for r in summary_rows
            if r["experiment_id"] == exp_id and r["variant"] == "control"
        )
        treatment = next(
            r for r in summary_rows
            if r["experiment_id"] == exp_id and r["variant"] == "treatment"
        )

        comparison = compare_variants(
            control["denominator_users"],
            control["numerator_users"],
            treatment["denominator_users"],
            treatment["numerator_users"],
            alpha,
        )

        for row in [control, treatment]:
            row.update(comparison)

        if exp.status == "running":
            for row in [control, treatment]:
                row["interpretation"] += " Registry status is running; treat as interim."

    summary = pd.DataFrame(summary_rows)
    integrity = pd.DataFrame(integrity_rows)

    SUMMARY_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(SUMMARY_OUTPUT, index=False)
    integrity.to_csv(INTEGRITY_OUTPUT, index=False)

    print("\nEVENT-LEVEL EXPERIMENT ANALYSIS")
    print("=" * 72)

    display_cols = [
        "experiment_id", "variant", "denominator_users",
        "numerator_users", "conversion_rate_pct",
    ]
    print("\nVARIANT CONVERSION RATES")
    print(summary[display_cols].to_string(index=False))

    comparison_cols = [
        "experiment_id", "absolute_lift_pp",
        "confidence_interval_low_pp", "confidence_interval_high_pp",
        "p_value", "statistically_significant",
    ]
    comparisons = summary[
        comparison_cols
    ].drop_duplicates(subset=["experiment_id"])

    print("\nEXPERIMENT-LEVEL TREATMENT COMPARISONS")
    print(comparisons.to_string(index=False))

    print("\nDATA INTEGRITY CHECKS")
    print("=" * 72)
    print(integrity.to_string(index=False))

    print("\nInterpretation notes:")
    print("- Rates use the registered experiment windows and eligible assignments.")
    print("- EXP-024 requires a later add_to_cart in the same session.")
    print("- EXP-025 requires a later purchase in the same session on mobile.")
    print("- The confidence interval is a normal-approximation interval.")
    print("- The p-value is a two-sided pooled two-proportion z-test.")
    print("- Target power is reported; achieved power is not calculated.")
    print("- Statistical significance does not establish causality or data quality.")
    print("- Synthetic results must not be presented as actual Puffy results.")
    print(f"\nSaved summary: {SUMMARY_OUTPUT}")
    print(f"Saved integrity report: {INTEGRITY_OUTPUT}")


if __name__ == "__main__":
    main()


import pandas as pd
import pytest

from experimentation.analyze_event_experiments import (
    ASSIGNMENTS_PATH,
    EVENTS_PATH,
    REGISTRY_PATH,
    as_bool,
    calculate_kpi,
    compare_variants,
    in_window,
    check_sample_ratio_mismatch,
    reconcile_denominator,
    deduplicate_by_id,
    exclude_conflicted_assignments,
    exclude_device_mismatches,
    main,
)

def make_event(
    event_id,
    event_name,
    timestamp,
    user_id="user-1",
    session_id="session-1",
    experiment_id="EXP-024",
    variant="control",
    device="desktop",
    product_id="product-1",
):
    return {
        "event_id": event_id,
        "event_name": event_name,
        "event_timestamp": pd.Timestamp(timestamp, tz="UTC"),
        "user_id": user_id,
        "session_id": session_id,
        "experiment_id": experiment_id,
        "experiment_variant": variant,
        "device_category": device,
        "product_id": product_id,
    }


def test_as_bool_parses_expected_values():
    result = as_bool(
        pd.Series(["True", "FALSE", "1", "0", "unknown"])
    )

    assert result.iloc[0] == True
    assert result.iloc[1] == False
    assert result.iloc[2] == True
    assert result.iloc[3] == False
    assert pd.isna(result.iloc[4])



def test_in_window_includes_start_and_end_calendar_day():
    timestamps = pd.Series(
        pd.to_datetime(
            [
                "2026-07-01T00:00:00Z",
                "2026-07-30T23:59:59Z",
                "2026-07-31T00:00:00Z",
            ],
            utc=True,
        )
    )

    result = in_window(
        timestamps,
        pd.to_datetime("2026-07-01", utc=True),
        pd.to_datetime("2026-07-30", utc=True),
    )

    assert result.tolist() == [True, True, False]


def test_exp024_counts_only_later_add_to_cart_in_same_session():
    assignments = pd.DataFrame([
        {"user_id": "user-1", "device_category": "desktop"},
        {"user_id": "user-2", "device_category": "desktop"},
        {"user_id": "user-3", "device_category": "desktop"},
    ])

    events = pd.DataFrame([
        make_event("e1", "view_item", "2026-07-02T10:00:00"),
        make_event(
            "e2", "add_to_cart", "2026-07-02T10:01:00",
        ),
        make_event(
            "e3", "view_item", "2026-07-02T11:00:00",
            user_id="user-2", session_id="session-2",
        ),
        make_event(
            "e4", "add_to_cart", "2026-07-02T10:59:00",
            user_id="user-2", session_id="session-2",
        ),
        make_event(
            "e5", "view_item", "2026-07-02T12:00:00",
            user_id="user-3", session_id="session-3",
        ),
        make_event(
            "e6", "add_to_cart", "2026-07-02T12:01:00",
            user_id="user-3", session_id="different-session",
        ),
    ])

    denominator_event, numerator_event, denominator, numerator = (
        calculate_kpi("EXP-024", assignments, events)
    )

    assert denominator_event == "view_item"
    assert numerator_event == "add_to_cart"
    assert denominator == {"user-1", "user-2", "user-3"}
    assert numerator == {"user-1"}


def test_exp025_counts_mobile_checkout_to_purchase_only():
    assignments = pd.DataFrame([
        {"user_id": "user-1", "device_category": "mobile"},
        {"user_id": "user-2", "device_category": "mobile"},
        {"user_id": "user-3", "device_category": "desktop"},
    ])

    events = pd.DataFrame([
        make_event(
            "e1", "begin_checkout", "2026-07-20T10:00:00",
            user_id="user-1", experiment_id="EXP-025",
            device="mobile",
        ),
        make_event(
            "e2", "purchase", "2026-07-20T10:05:00",
            user_id="user-1", experiment_id="EXP-025",
            device="mobile",
        ),
        make_event(
            "e3", "begin_checkout", "2026-07-20T11:00:00",
            user_id="user-2", session_id="session-2",
            experiment_id="EXP-025", device="mobile",
        ),
        make_event(
            "e4", "purchase", "2026-07-20T11:05:00",
            user_id="user-2", session_id="different-session",
            experiment_id="EXP-025", device="mobile",
        ),
        make_event(
            "e5", "begin_checkout", "2026-07-20T12:00:00",
            user_id="user-3", session_id="session-3",
            experiment_id="EXP-025", device="desktop",
        ),
        make_event(
            "e6", "purchase", "2026-07-20T12:05:00",
            user_id="user-3", session_id="session-3",
            experiment_id="EXP-025", device="desktop",
        ),
    ])

    denominator_event, numerator_event, denominator, numerator = (
        calculate_kpi("EXP-025", assignments, events)
    )

    assert denominator_event == "begin_checkout"
    assert numerator_event == "purchase"
    assert denominator == {"user-1", "user-2"}
    assert numerator == {"user-1"}


def test_compare_variants_detects_clear_difference():
    result = compare_variants(
        control_n=1000,
        control_x=200,
        treatment_n=1000,
        treatment_x=300,
        alpha=0.05,
    )

    assert result["absolute_lift_pp"] == pytest.approx(10.0)
    assert result["p_value"] < 0.05
    assert result["statistically_significant"] is True
    assert result["confidence_interval_low_pp"] < 10.0
    assert result["confidence_interval_high_pp"] > 10.0


def test_compare_variants_handles_empty_variant():
    result = compare_variants(
        control_n=0,
        control_x=0,
        treatment_n=100,
        treatment_x=20,
        alpha=0.05,
    )

    assert pd.isna(result["p_value"])
    assert result["statistically_significant"] is False


def test_calculate_kpi_rejects_unknown_experiment():
    assignments = pd.DataFrame(
        [{"user_id": "user-1", "device_category": "desktop"}]
    )
    events = pd.DataFrame(
        columns=[
            "experiment_id", "user_id", "session_id",
            "event_name", "event_timestamp", "product_id",
            "device_category",
        ]
    )

    with pytest.raises(ValueError, match="No event-level KPI definition"):
        calculate_kpi("EXP-999", assignments, events)


def test_srm_does_not_flag_balanced_assignment():
    result = check_sample_ratio_mismatch(
        control_n=500,
        treatment_n=500,
    )

    assert result["srm_p_value"] == pytest.approx(1.0)
    assert result["srm_detected"] is False


def test_srm_flags_materially_imbalanced_assignment():
    result = check_sample_ratio_mismatch(
        control_n=600,
        treatment_n=400,
    )

    assert result["srm_p_value"] < 0.001
    assert result["srm_detected"] is True

def test_reconcile_denominator_counts_qualified_and_missing_users():
    assignments = pd.DataFrame({
        "user_id": ["u1", "u2", "u3", "u3"],
    })

    result = reconcile_denominator(
        assignments,
        {"u1", "u3", "outsider"},
    )

    assert result["eligible_assigned_users"] == 3
    assert result["denominator_users"] == 2
    assert result["eligible_users_without_denominator_event"] == 1
    assert result["denominator_reconciles"] is True


def test_reconcile_denominator_handles_no_qualifying_users():
    assignments = pd.DataFrame({
        "user_id": ["u1", "u2"],
    })

    result = reconcile_denominator(assignments, set())

    assert result["eligible_assigned_users"] == 2
    assert result["denominator_users"] == 0
    assert result["eligible_users_without_denominator_event"] == 2
    assert result["denominator_reconciles"] is True

def test_deduplicate_by_id_keeps_one_exact_duplicate():
    df = pd.DataFrame([
        {"event_id": "e1", "user_id": "user-1", "event_name": "view_item"},
        {"event_id": "e1", "user_id": "user-1", "event_name": "view_item"},
        {"event_id": "e2", "user_id": "u2", "event_name": "purchase"},
    ])

    cleaned, exact_duplicates, conflicting_duplicates, missing_ids = (
        deduplicate_by_id(df, "event_id")
    )

    assert missing_ids == 0
    assert len(cleaned) == 2
    assert exact_duplicates == 1
    assert conflicting_duplicates == 0


def test_deduplicate_by_id_excludes_conflicting_duplicate_ids():
    df = pd.DataFrame([
        {"event_id": "e1", "user_id": "user-1", "event_name": "view_item"},
        {"event_id": "e1", "user_id": "u2", "event_name": "purchase"},
        {"event_id": "e2", "user_id": "u3", "event_name": "view_item"},
    ])

    cleaned, exact_duplicates, conflicting_duplicates, missing_ids = (
        deduplicate_by_id(df, "event_id")
    )

    assert cleaned["event_id"].tolist() == ["e2"]
    assert exact_duplicates == 0
    assert conflicting_duplicates == 1


def exclude_conflicted_assignments(assignments):
    """
    Exclude assignments with missing identifiers and users with
    multiple distinct assignments in the same experiment.

    Returns:
        cleaned_assignments,
        conflicted_user_count,
        missing_identifier_count
    """
    assignments = assignments.copy()

    required_columns = [
        "experiment_id",
        "user_id",
        "assignment_id",
    ]

    missing_identifier_mask = assignments[
        required_columns
    ].isna().any(axis=1)

    missing_identifier_count = int(
        missing_identifier_mask.sum()
    )

    identified = assignments.loc[
        ~missing_identifier_mask
    ].copy()

    assignment_counts = (
        identified.groupby(
            ["experiment_id", "user_id"]
        )["assignment_id"]
        .nunique()
    )

    conflicted = assignment_counts[assignment_counts > 1]
    conflicted_users = set(conflicted.index.tolist())

    user_keys = list(
        zip(
            identified["experiment_id"],
            identified["user_id"],
        )
    )

    keep_mask = pd.Series(
        [key not in conflicted_users for key in user_keys],
        index=identified.index,
    )

    cleaned = identified.loc[keep_mask].copy()

    return (
        cleaned,
        len(conflicted_users),
        missing_identifier_count,
    )

def test_exclude_device_mismatches_keeps_valid_events():
    assignments = pd.DataFrame([
        {
            "experiment_id": "EXP-024",
            "user_id": "user-1",
            "device_category": "desktop",
        }
    ])

    events = pd.DataFrame([
        make_event(
            "e1", "view_item", "2026-07-02T10:00:00",
            device="desktop",
        ),
        make_event(
            "e2", "add_to_cart", "2026-07-02T10:01:00",
            device="mobile",
        ),
        make_event(
            "e3", "purchase", "2026-07-02T10:02:00",
            device="desktop",
        ),
    ])

    cleaned, mismatch_count, missing_device_count = (
        exclude_device_mismatches(events, assignments)
    )

    assert cleaned["event_id"].tolist() == ["e1", "e3"]
    assert mismatch_count == 1
    assert missing_device_count == 0

def test_deduplicate_by_id_excludes_and_counts_missing_ids():
    df = pd.DataFrame([
        {"event_id": "e1", "user_id": "u1", "event_name": "view_item"},
        {"event_id": None, "user_id": "u2", "event_name": "purchase"},
        {"event_id": "e2", "user_id": "u3", "event_name": "purchase"},
    ])

    (
        cleaned,
        exact_duplicates,
        conflicting_duplicates,
        missing_ids,
    ) = deduplicate_by_id(df, "event_id")

    assert cleaned["event_id"].tolist() == ["e1", "e2"]
    assert exact_duplicates == 0
    assert conflicting_duplicates == 0
    assert missing_ids == 1

def test_deduplicate_assignments_excludes_conflicting_assignment_ids():
    assignments = pd.DataFrame([
        {
            "assignment_id": "a1",
            "experiment_id": "EXP-024",
            "user_id": "u1",
            "variant": "control",
        },
        {
            "assignment_id": "a1",
            "experiment_id": "EXP-024",
            "user_id": "u1",
            "variant": "treatment",
        },
        {
            "assignment_id": "a2",
            "experiment_id": "EXP-024",
            "user_id": "u2",
            "variant": "control",
        },
    ])

    (
        cleaned,
        exact_duplicates,
        conflicting_duplicates,
        missing_ids,
    ) = deduplicate_by_id(assignments, "assignment_id")

    assert cleaned["assignment_id"].tolist() == ["a2"]
    assert exact_duplicates == 0
    assert conflicting_duplicates == 1
    assert missing_ids == 0

def test_deduplicate_by_id_conflicts_are_independent_of_row_order():
    df = pd.DataFrame([
        {"event_id": "e1", "user_id": "u1", "event_name": "view_item"},
        {"event_id": "e1", "user_id": "u2", "event_name": "purchase"},
        {"event_id": "e2", "user_id": "u3", "event_name": "purchase"},
    ])

    forward = deduplicate_by_id(df, "event_id")
    reversed_result = deduplicate_by_id(
        df.iloc[::-1].reset_index(drop=True),
        "event_id",
    )

    assert forward[0]["event_id"].tolist() == ["e2"]
    assert reversed_result[0]["event_id"].tolist() == ["e2"]
    assert forward[2:] == reversed_result[2:]

def test_exclude_device_mismatches_preserves_unmatched_events():
    assignments = pd.DataFrame([
        {
            "experiment_id": "EXP-024",
            "user_id": "user-1",
            "device_category": "desktop",
        }
    ])

    events = pd.DataFrame([
        make_event(
            "e1", "view_item", "2026-07-02T10:00:00",
            device="desktop",
        ),
        make_event(
            "e2", "purchase", "2026-07-02T10:01:00",
            device="mobile",
            user_id="unmatched-user",
        ),
    ])

    cleaned, mismatch_count, missing_device_count = (
        exclude_device_mismatches(events, assignments)
    )

    assert cleaned["event_id"].tolist() == ["e1", "e2"]
    assert mismatch_count == 0
    assert missing_device_count == 0

def test_exclude_conflicted_assignments_excludes_missing_identifiers():
    assignments = pd.DataFrame([
        {
            "experiment_id": "EXP-024",
            "user_id": "u1",
            "assignment_id": "a1",
            "variant": "control",
        },
        {
            "experiment_id": "EXP-024",
            "user_id": None,
            "assignment_id": "a2",
            "variant": "control",
        },
        {
            "experiment_id": "EXP-024",
            "user_id": "u3",
            "assignment_id": None,
            "variant": "treatment",
        },
        {
            "experiment_id": None,
            "user_id": "u4",
            "assignment_id": "a4",
            "variant": "control",
        },
    ])

    (
        cleaned,
        conflicted_users,
        missing_identifier_count,
    ) = exclude_conflicted_assignments(assignments)

    assert cleaned["assignment_id"].tolist() == ["a1"]
    assert conflicted_users == 0
    assert missing_identifier_count == 3

def test_main_handles_injected_data_quality_anomalies(tmp_path):
    assignments = pd.read_csv(ASSIGNMENTS_PATH)
    events = pd.read_csv(EVENTS_PATH)

    # Inject assignment anomalies.
    exact_duplicate_assignment = assignments.iloc[[0]].copy()

    conflicting_assignment = assignments.iloc[[1]].copy()
    conflicting_assignment.loc[:, "user_id"] = "EXP-024_CONFLICTING_USER"

    missing_assignment_id = assignments.iloc[[2]].copy()
    missing_assignment_id.loc[:, "assignment_id"] = None

    conflicted_user_assignment = assignments.iloc[[3]].copy()
    conflicted_user_assignment.loc[:, "assignment_id"] = (
        "EXP_ASSIGN_INJECTED_CONFLICT"
    )

    assignments = pd.concat(
        [
            assignments,
            exact_duplicate_assignment,
            conflicting_assignment,
            missing_assignment_id,
            conflicted_user_assignment,
        ],
        ignore_index=True,
    )

    # Inject event anomalies.
    exact_duplicate_event = events.iloc[[0]].copy()

    conflicting_event = events.iloc[[3]].copy()
    conflicting_event.loc[:, "event_name"] = "injected_conflicting_event"

    missing_event_id = events.iloc[[5]].copy()
    missing_event_id.loc[:, "event_id"] = None

    # Modify existing events so their IDs remain unique.
    events.loc[9, "device_category"] = "injected_device"
    events.loc[10, "device_category"] = None

    events = pd.concat(
        [
            events,
            exact_duplicate_event,
            conflicting_event,
            missing_event_id,
        ],
        ignore_index=True,
    )
    # Write modified inputs into pytest's temporary directory.
    assignments_path = tmp_path / "assignments.csv"
    events_path = tmp_path / "events.csv"
    summary_path = tmp_path / "output" / "summary.csv"
    integrity_path = tmp_path / "output" / "integrity.csv"

    assignments.to_csv(assignments_path, index=False)
    events.to_csv(events_path, index=False)

    # Run the real analyzer against the temporary datasets.
    main(
        registry_path=REGISTRY_PATH,
        assignments_path=assignments_path,
        events_path=events_path,
        summary_output=summary_path,
        integrity_output=integrity_path,
    )

    # Read the generated integrity report.
    integrity = pd.read_csv(integrity_path)
    exp024 = integrity.loc[
        integrity["experiment_id"] == "EXP-024"
    ].iloc[0]

    # Verify assignment safeguards.
    assert exp024["exact_duplicate_assignment_rows"] == 1
    assert exp024["conflicting_assignment_ids"] == 1
    assert exp024["missing_assignment_ids"] == 1
    assert exp024["conflicted_assignment_users"] == 1

    # Verify event safeguards.
    assert exp024["exact_duplicate_event_rows"] == 1
    assert exp024["conflicting_event_ids"] == 1
    assert exp024["missing_event_ids"] == 1
    assert exp024["device_mismatches"] == 1
    assert exp024["missing_event_devices"] == 1

    # Verify that both output reports were generated.
    assert summary_path.exists()
    assert integrity_path.exists()
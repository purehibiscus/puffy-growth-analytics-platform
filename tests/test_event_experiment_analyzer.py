
import pandas as pd
import pytest

from experimentation.analyze_event_experiments import (
    as_bool,
    calculate_kpi,
    compare_variants,
    in_window,
    check_sample_ratio_mismatch,
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

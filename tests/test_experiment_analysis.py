
import math
import pandas as pd
import pytest
from experimentation import analyze_experiments
from experimentation.analyze_experiments import analyze_experiment


def make_experiment(status="completed"):
    return pd.Series({
        "experiment_id": "EXP-TEST",
        "start_date": "2026-07-01",
        "end_date": "2026-07-30",
        "status": status,
        "primary_kpi": "test_kpi",
        "alpha": 0.05,
        "power": 0.8,
    })


def make_assignments():
    return pd.DataFrame([
        {
            "assignment_id": "A1",
            "experiment_id": "EXP-TEST",
            "user_id": "U1",
            "assignment_timestamp": pd.Timestamp("2026-07-10 10:00:00"),
            "variant": "control",
            "eligible": True,
            "converted": 0,
            "revenue": 0.0,
            "checkout_completed": 0,
            "guardrail_refund": 0,
        },
        {
            "assignment_id": "A2",
            "experiment_id": "EXP-TEST",
            "user_id": "U2",
            "assignment_timestamp": pd.Timestamp("2026-07-11 10:00:00"),
            "variant": "treatment",
            "eligible": True,
            "converted": 1,
            "revenue": 50.0,
            "checkout_completed": 1,
            "guardrail_refund": 0,
        },
        {
            "assignment_id": "A3",
            "experiment_id": "EXP-TEST",
            "user_id": "U3",
            "assignment_timestamp": pd.Timestamp("2026-07-12 10:00:00"),
            "variant": "control",
            "eligible": True,
            "converted": 1,
            "revenue": 20.0,
            "checkout_completed": 0,
            "guardrail_refund": 1,
        },
        {
            "assignment_id": "A4",
            "experiment_id": "EXP-TEST",
            "user_id": "U4",
            "assignment_timestamp": pd.Timestamp("2026-07-31 10:00:00"),
            "variant": "treatment",
            "eligible": True,
            "converted": 1,
            "revenue": 100.0,
            "checkout_completed": 1,
            "guardrail_refund": 0,
        },
        {
            "assignment_id": "A5",
            "experiment_id": "EXP-TEST",
            "user_id": "U5",
            "assignment_timestamp": pd.Timestamp("2026-07-15 10:00:00"),
            "variant": "treatment",
            "eligible": False,
            "converted": 1,
            "revenue": 75.0,
            "checkout_completed": 1,
            "guardrail_refund": 0,
        },
    ])


def test_analysis_filters_date_window_and_ineligible_rows():
    result = analyze_experiment(make_experiment(), make_assignments())

    control = result[result["variant"] == "control"].iloc[0]
    treatment = result[result["variant"] == "treatment"].iloc[0]

    assert control["eligible_assignments"] == 2
    assert treatment["eligible_assignments"] == 1
    assert "1 assignment(s) outside experiment window" in (
        treatment["assignment_integrity_warning"]
    )
    assert "1 ineligible assignment(s) inside window" in (
        treatment["assignment_integrity_warning"]
    )


def test_variant_metrics_are_calculated_correctly():
    result = analyze_experiment(make_experiment(), make_assignments())

    control = result[result["variant"] == "control"].iloc[0]
    treatment = result[result["variant"] == "treatment"].iloc[0]

    assert control["conversions"] == 1
    assert control["converted_flag_rate"] == 0.5
    assert control["revenue_per_assignment"] == 10.0
    assert control["checkout_completion_rate"] == 0.0
    assert control["refund_guardrail_rate"] == 0.5

    assert treatment["conversions"] == 1
    assert treatment["converted_flag_rate"] == 1.0
    assert treatment["revenue_per_assignment"] == 50.0
    assert treatment["checkout_completion_rate"] == 1.0
    assert treatment["refund_guardrail_rate"] == 0.0


def test_clean_assignments_receive_finite_confidence_interval():
    assignments = make_assignments().iloc[:3].copy()

    result = analyze_experiment(make_experiment(), assignments)

    assert result["conversion_ci95_low"].notna().all()
    assert result["conversion_ci95_high"].notna().all()
    assert math.isclose(
        result["converted_flag_absolute_difference"].iloc[0],
        0.5,
    )


def test_repeated_users_suppress_confidence_interval():
    assignments = make_assignments().iloc[:3].copy()
    repeated = assignments.iloc[[0]].copy()
    repeated["assignment_id"] = "A6"
    repeated["assignment_timestamp"] = pd.Timestamp("2026-07-13 10:00:00")
    assignments = pd.concat([assignments, repeated], ignore_index=True)

    result = analyze_experiment(make_experiment(), assignments)

    assert result["conversion_ci95_low"].isna().all()
    assert result["conversion_ci95_high"].isna().all()
    assert result["assignment_integrity_warning"].str.contains(
        "repeated users"
    ).all()


def test_cross_variant_users_suppress_confidence_interval():
    assignments = make_assignments().iloc[:3].copy()
    cross_variant = assignments.iloc[[0]].copy()
    cross_variant["assignment_id"] = "A7"
    cross_variant["variant"] = "treatment"
    cross_variant["assignment_timestamp"] = pd.Timestamp("2026-07-14 10:00:00")
    assignments = pd.concat([assignments, cross_variant], ignore_index=True)

    result = analyze_experiment(make_experiment(), assignments)

    assert result["conversion_ci95_low"].isna().all()
    assert result["conversion_ci95_high"].isna().all()
    assert result["assignment_integrity_warning"].str.contains(
        "multiple variants"
    ).all()


def test_running_experiment_is_marked_interim():
    result = analyze_experiment(
        make_experiment(status="running"),
        make_assignments().iloc[:3].copy(),
    )

    assert result["result_maturity"].str.contains("INTERIM").all()


def test_loader_rejects_duplicate_assignment_ids(monkeypatch):
    assignments = make_assignments()
    assignments.loc[1, "assignment_id"] = assignments.loc[0, "assignment_id"]

    def fake_read_csv(path):
        if str(path).endswith("experiments.csv"):
            return pd.DataFrame([make_experiment()])
        return assignments.copy()

    monkeypatch.setattr(analyze_experiments.pd, "read_csv", fake_read_csv)

    with pytest.raises(ValueError, match="Duplicate assignment IDs"):
        analyze_experiments.load_experiment_data()


def test_loader_rejects_invalid_timestamp(monkeypatch):
    assignments = make_assignments()
    assignments["assignment_timestamp"] = assignments["assignment_timestamp"].astype("string")
    assignments.loc[0, "assignment_timestamp"] = "not-a-timestamp"

    def fake_read_csv(path):
        if str(path).endswith("experiments.csv"):
            return pd.DataFrame([make_experiment()])
        return assignments.copy()

    monkeypatch.setattr(analyze_experiments.pd, "read_csv", fake_read_csv)

    with pytest.warns(UserWarning, match="Could not infer format"):
        with pytest.raises(ValueError, match="assignment timestamps"):
            analyze_experiments.load_experiment_data()

def test_loader_rejects_invalid_binary_flag(monkeypatch):
    assignments = make_assignments()
    assignments.loc[0, "converted"] = 2

    def fake_read_csv(path):
        if str(path).endswith("experiments.csv"):
            return pd.DataFrame([make_experiment()])
        return assignments.copy()

    monkeypatch.setattr(analyze_experiments.pd, "read_csv", fake_read_csv)

    with pytest.raises(ValueError, match="Non-binary values"):
        analyze_experiments.load_experiment_data()


def test_loader_rejects_negative_revenue(monkeypatch):
    assignments = make_assignments()
    assignments.loc[0, "revenue"] = -1

    def fake_read_csv(path):
        if str(path).endswith("experiments.csv"):
            return pd.DataFrame([make_experiment()])
        return assignments.copy()

    monkeypatch.setattr(analyze_experiments.pd, "read_csv", fake_read_csv)

    with pytest.raises(ValueError, match="Negative revenue"):
        analyze_experiments.load_experiment_data()

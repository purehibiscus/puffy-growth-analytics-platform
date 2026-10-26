
import importlib.util
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = PROJECT_ROOT / "scripts" / "generate_experiment_dataset.py"

spec = importlib.util.spec_from_file_location(
    "generate_experiment_dataset",
    GENERATOR_PATH,
)
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


def test_generation_is_deterministic():
    assignments_a, events_a = generator.generate_dataset(
        users_per_experiment=20, seed=42
    )
    assignments_b, events_b = generator.generate_dataset(
        users_per_experiment=20, seed=42
    )

    assert assignments_a == assignments_b
    assert events_a == events_b


def test_assignment_ids_and_event_ids_are_unique():
    assignments, events = generator.generate_dataset(
        users_per_experiment=30, seed=42
    )

    assert len({row["assignment_id"] for row in assignments}) == len(assignments)
    assert len({row["event_id"] for row in events}) == len(events)


def test_assignments_respect_registered_experiment_windows():
    assignments, _ = generator.generate_dataset(
        users_per_experiment=30, seed=42
    )

    for row in assignments:
        timestamp = pd.Timestamp(row["assignment_timestamp"])
        config = generator.EXPERIMENTS[row["experiment_id"]]

        assert config["start"] <= timestamp.date() <= config["end"]


def test_each_user_has_one_assignment_per_experiment():
    assignments, _ = generator.generate_dataset(
        users_per_experiment=30, seed=42
    )
    pairs = [(row["experiment_id"], row["user_id"]) for row in assignments]

    assert len(pairs) == len(set(pairs))


def test_exp025_assignments_are_mobile_only():
    assignments, _ = generator.generate_dataset(
        users_per_experiment=30, seed=42
    )
    exp025 = [row for row in assignments if row["experiment_id"] == "EXP-025"]

    assert exp025
    assert all(row["device_category"] == "mobile" for row in exp025)


def test_event_variant_and_identity_match_assignment():
    assignments, events = generator.generate_dataset(
        users_per_experiment=30, seed=42
    )
    assignment_by_user = {
        (row["experiment_id"], row["user_id"]): row for row in assignments
    }

    for event in events:
        assignment = assignment_by_user[
            (event["experiment_id"], event["user_id"])
        ]
        assert event["experiment_variant"] == assignment["variant"]
        assert event["device_category"] == assignment["device_category"]


def test_event_timestamps_are_ordered_within_each_session():
    _, events = generator.generate_dataset(
        users_per_experiment=30, seed=42
    )
    frame = pd.DataFrame(events)
    frame["event_timestamp"] = pd.to_datetime(frame["event_timestamp"])

    for _, session in frame.groupby("session_id"):
        assert session["event_timestamp"].is_monotonic_increasing


def test_conversion_flags_match_primary_kpi_events():
    assignments, events = generator.generate_dataset(
        users_per_experiment=50, seed=42
    )
    events_by_user = {}

    for event in events:
        key = (event["experiment_id"], event["user_id"])
        events_by_user.setdefault(key, set()).add(event["event_name"])

    for assignment in assignments:
        key = (assignment["experiment_id"], assignment["user_id"])
        event_names = events_by_user.get(key, set())

        if assignment["experiment_id"] == "EXP-024":
            expected_conversion = int(
                "view_item" in event_names and "add_to_cart" in event_names
            )
        else:
            expected_conversion = int(
                "begin_checkout" in event_names and "purchase" in event_names
            )

        assert assignment["converted"] == expected_conversion


def test_invalid_sample_size_is_rejected():
    try:
        generator.generate_dataset(users_per_experiment=0, seed=42)
    except ValueError as exc:
        assert "at least 1" in str(exc)
    else:
        raise AssertionError("Expected zero users to be rejected")


def test_browser_and_os_are_consistent_within_each_session():
    _, events = generator.generate_dataset(
        users_per_experiment=30, seed=42
    )
    frame = pd.DataFrame(events)

    assert (frame.groupby("session_id")["browser"].nunique() == 1).all()
    assert (frame.groupby("session_id")["os"].nunique() == 1).all()
    assert (frame.groupby("session_id")["device_category"].nunique() == 1).all()


def test_conversion_flags_match_funnel_events():
    assignments, events = generator.generate_dataset(
        users_per_experiment=50, seed=42
    )

    event_groups = {
        (experiment_id, user_id): group.sort_values("event_timestamp")[
            "event_name"
        ].tolist()
        for (experiment_id, user_id), group in pd.DataFrame(events).groupby(
            ["experiment_id", "user_id"]
        )
    }

    for assignment in assignments:
        names = event_groups[
            (assignment["experiment_id"], assignment["user_id"])
        ]

        if assignment["experiment_id"] == "EXP-024":
            expected = int(
                "view_item" in names
                and "add_to_cart" in names
                and names.index("add_to_cart") > names.index("view_item")
            )
        else:
            expected = int(
                "begin_checkout" in names
                and "purchase" in names
                and names.index("purchase") > names.index("begin_checkout")
            )
            assert assignment["checkout_completed"] == int("purchase" in names)

        assert assignment["converted"] == expected

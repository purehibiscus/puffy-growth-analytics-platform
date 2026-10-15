import importlib.util
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = PROJECT_ROOT / "scripts" / "generate_ga4_events.py"

spec = importlib.util.spec_from_file_location(
    "generate_ga4_events",
    GENERATOR_PATH,
)
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


EXPECTED_COLUMNS = [
    "event_id",
    "event_timestamp",
    "user_id",
    "session_id",
    "event_name",
    "page_location",
    "device_category",
    "country",
    "traffic_source",
    "traffic_medium",
    "campaign",
    "landing_page",
    "product_id",
    "experiment_id",
    "experiment_variant",
    "browser",
    "os",
    "engagement_seconds",
    "scroll_depth_pct",
    "page_load_ms",
]


def generate_to_path(path, rows=1000, seed=42):
    generator.generate_events(
        rows=rows,
        seed=seed,
        days=60,
        output=path,
        chunk_size=100,
    )
    return pd.read_csv(path)


def test_exact_row_count_and_schema(tmp_path):
    output = tmp_path / "events.csv"
    df = generate_to_path(output, rows=1000)

    assert len(df) == 1000
    assert df.columns.tolist() == EXPECTED_COLUMNS


def test_event_ids_are_unique_and_values_are_complete(tmp_path):
    df = generate_to_path(tmp_path / "events.csv")

    assert df["event_id"].is_unique
    assert not df.isna().any().any()


def test_session_timestamps_are_chronological(tmp_path):
    df = generate_to_path(tmp_path / "events.csv")
    df["event_timestamp"] = pd.to_datetime(df["event_timestamp"])

    ordered = df.groupby("session_id")["event_timestamp"].apply(
        lambda values: values.is_monotonic_increasing
    )

    assert ordered.all()


def test_every_session_starts_with_session_start(tmp_path):
    df = generate_to_path(tmp_path / "events.csv")

    for _, group in df.groupby("session_id", sort=False):
        events = group["event_name"].tolist()
        assert events[0] == "session_start"

        if len(events) > 1:
            assert events[1] == "view_item"


def test_purchase_requires_complete_funnel(tmp_path):
    df = generate_to_path(tmp_path / "events.csv")

    required_before_purchase = [
        "session_start",
        "view_item",
        "add_to_cart",
        "begin_checkout",
        "add_payment_info",
    ]

    for _, group in df.groupby("session_id", sort=False):
        events = group.sort_values("event_timestamp")[
            "event_name"
        ].tolist()

        if "purchase" not in events:
            continue

        purchase_position = events.index("purchase")
        preceding = events[:purchase_position]

        assert all(
            event in preceding
            for event in required_before_purchase
        )


def test_same_seed_produces_identical_data(tmp_path):
    first = generate_to_path(
        tmp_path / "first.csv",
        rows=500,
        seed=42,
    )
    second = generate_to_path(
        tmp_path / "second.csv",
        rows=500,
        seed=42,
    )

    pd.testing.assert_frame_equal(first, second)


def test_different_seeds_change_generated_data(tmp_path):
    first = generate_to_path(
        tmp_path / "first.csv",
        rows=500,
        seed=42,
    )
    second = generate_to_path(
        tmp_path / "second.csv",
        rows=500,
        seed=99,
    )

    assert not first.equals(second)
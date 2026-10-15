
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATASETS = {
    "Original": PROJECT_ROOT / "data" / "synthetic" / "ga4_events.csv",
    "Corrected Candidate": (
        PROJECT_ROOT / "data" / "synthetic" / "ga4_events_corrected_candidate.csv"
    ),
    "Small Generated Test": (
        PROJECT_ROOT / "data" / "synthetic" / "ga4_events_generated.csv"
    ),
}

FUNNEL_STAGES = [
    "session_start",
    "view_item",
    "add_to_cart",
    "begin_checkout",
    "add_payment_info",
    "purchase",
]


def summarize_dataset(name, path):
    if not path.exists():
        raise FileNotFoundError(f"{name} dataset not found: {path}")

    df = pd.read_csv(
        path,
        usecols=["event_name", "session_id", "event_timestamp"],
    )

    df["event_timestamp"] = pd.to_datetime(
        df["event_timestamp"], errors="coerce", utc=True
    )
    df = df.dropna(subset=["session_id", "event_name", "event_timestamp"])
    df["event_name"] = df["event_name"].astype(str).str.strip().str.lower()

    sessions = (
        df.sort_values(["session_id", "event_timestamp"])
        .groupby("session_id", sort=False)["event_name"]
        .agg(list)
    )

    print(f"\n{'=' * 68}")
    print(name.upper())
    print(f"File: {path.name}")
    print(f"{'=' * 68}")
    print(f"Events with valid session, event name and timestamp: {len(df):,}")
    print(f"Sessions: {len(sessions):,}")
    print(f"Unique event names: {df['event_name'].nunique()}")

    print("\nEvent distribution (% of events):")
    print(
        df["event_name"]
        .value_counts(normalize=True)
        .mul(100)
        .round(2)
        .to_string()
    )

    presence_counts = {
        stage: int(sessions.apply(lambda events: stage in events).sum())
        for stage in FUNNEL_STAGES
    }

    print("\nStage presence (order ignored):")
    for stage in FUNNEL_STAGES:
        print(f"{stage:20s} {presence_counts[stage]:,}")

    ordered_counts = {stage: 0 for stage in FUNNEL_STAGES}

    for events in sessions:
        position = 0

        for stage in FUNNEL_STAGES:
            try:
                position = events.index(stage, position) + 1
                ordered_counts[stage] += 1
            except ValueError:
                break

    funnel = pd.DataFrame({
        "stage": FUNNEL_STAGES,
        "sessions_reaching_stage_in_order": [
            ordered_counts[stage] for stage in FUNNEL_STAGES
        ],
    })

    funnel["conversion_from_previous_stage_pct"] = (
        funnel["sessions_reaching_stage_in_order"]
        .div(funnel["sessions_reaching_stage_in_order"].shift(1))
        .mul(100)
        .round(2)
    )
    funnel.loc[0, "conversion_from_previous_stage_pct"] = 100.0

    print("\nStrictly ordered funnel:")
    print(funnel.to_string(index=False))


def main():
    for name, path in DATASETS.items():
        summarize_dataset(name, path)


if __name__ == "__main__":
    main()

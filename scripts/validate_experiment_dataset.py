
from pathlib import Path

import pandas as pd

DATA_DIR = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "synthetic"
    / "experiment_dataset"
)


def main():
    assignments = pd.read_csv(DATA_DIR / "experiment_assignments.csv")
    events = pd.read_csv(DATA_DIR / "ga4_experiment_events.csv")
    events["event_timestamp"] = pd.to_datetime(events["event_timestamp"])

    failures = []
    groups = {
        (experiment_id, user_id): group.sort_values("event_timestamp")["event_name"].tolist()
        for (experiment_id, user_id), group in events.groupby(
            ["experiment_id", "user_id"]
        )
    }

    for _, row in assignments.iterrows():
        names = groups.get((row["experiment_id"], row["user_id"]), [])

        if row["experiment_id"] == "EXP-024":
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

        if int(row["converted"]) != expected:
            failures.append(
                (row["experiment_id"], row["user_id"], "conversion flag")
            )

        if row["experiment_id"] == "EXP-025":
            expected_checkout = int("purchase" in names)
            if int(row["checkout_completed"]) != expected_checkout:
                failures.append(
                    (row["experiment_id"], row["user_id"], "checkout flag")
                )

    exp024 = events[events["experiment_id"] == "EXP-024"]
    exp025 = events[events["experiment_id"] == "EXP-025"]

    print("Assignments:", len(assignments))
    print("Events:", len(events))
    print("Conversion/checkout flag failures:", len(failures))
    print("Sample failures:", failures[:5])
    print(
        "All EXP-025 assignments mobile:",
        bool(
            (
                assignments.loc[
                    assignments["experiment_id"] == "EXP-025",
                    "device_category",
                ]
                == "mobile"
            ).all()
        ),
    )
    print(
        "All EXP-024 users have view_item:",
        bool(
            exp024.groupby("user_id")["event_name"]
            .apply(lambda names: names.eq("view_item").any())
            .all()
        ),
    )
    print(
        "All EXP-025 users have begin_checkout:",
        bool(
            exp025.groupby("user_id")["event_name"]
            .apply(lambda names: names.eq("begin_checkout").any())
            .all()
        ),
    )


if __name__ == "__main__":
    main()

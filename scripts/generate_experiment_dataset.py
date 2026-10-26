
"""Generate isolated, reproducible synthetic data for EXP-024 and EXP-025.

This dataset is fictional and must not be interpreted as real Puffy data.
Existing project CSVs are never modified by this script.
"""

import argparse
import csv
import random
from datetime import date, datetime, time, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "data" / "synthetic" / "experiment_dataset"

ASSIGNMENT_COLUMNS = [
    "assignment_id",
    "experiment_id",
    "user_id",
    "assignment_timestamp",
    "variant",
    "device_category",
    "traffic_source",
    "country",
    "product_id",
    "eligible",
    "converted",
    "revenue",
    "checkout_completed",
    "guardrail_refund",
]

EVENT_COLUMNS = [
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

EXPERIMENTS = {
    "EXP-024": {
        "start": date(2026, 7, 1),
        "end": date(2026, 7, 30),
        "kpi": "product_page_to_cart",
    },
    "EXP-025": {
        "start": date(2026, 7, 15),
        "end": date(2026, 8, 15),
        "kpi": "checkout_to_purchase",
    },
}

TRAFFIC_SOURCES = ["google", "meta", "organic", "direct"]
COUNTRIES = ["US", "Canada", "UK", "UAE"]
PRODUCT_IDS = [f"PROD-{number:04d}" for number in range(1, 101)]


def random_timestamp(rng, start_date, end_date):
    """Return a random timestamp within the inclusive date range."""
    day_count = (end_date - start_date).days
    chosen_date = start_date + timedelta(days=rng.randint(0, day_count))
    chosen_time = time(
        hour=rng.randrange(24),
        minute=rng.randrange(60),
        second=rng.randrange(60),
    )
    return datetime.combine(chosen_date, chosen_time)


def make_event(
    event_id,
    timestamp,
    user_id,
    session_id,
    event_name,
    experiment_id,
    variant,
    device,
    country,
    source,
    product_id,
    browser,
    os_name,
    rng,
):
    """Create one complete event record using the project's GA4-like schema."""
    page_by_event = {
        "session_start": "/",
        "view_item": f"/products/{product_id.lower()}",
        "add_to_cart": "/cart",
        "begin_checkout": "/checkout",
        "add_payment_info": "/checkout/payment",
        "purchase": "/checkout/confirmation",
    }

    return {
        "event_id": event_id,
        "event_timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        "user_id": user_id,
        "session_id": session_id,
        "event_name": event_name,
        "page_location": page_by_event[event_name],
        "device_category": device,
        "country": country,
        "traffic_source": source,
        "traffic_medium": "organic" if source == "organic" else "paid",
        "campaign": "synthetic_experiment",
        "landing_page": "/",
        "product_id": product_id,
        "experiment_id": experiment_id,
        "experiment_variant": variant,
        "browser": browser,
        "os": os_name,
        "engagement_seconds": rng.randint(1, 180),
        "scroll_depth_pct": rng.choice([25, 50, 75, 90, 100]),
        "page_load_ms": rng.randint(300, 3000),
    }


def generate_dataset(users_per_experiment=1000, seed=42):
    """Return assignment and event records without writing to source datasets."""
    if users_per_experiment < 1:
        raise ValueError("users_per_experiment must be at least 1")

    rng = random.Random(seed)
    assignments = []
    events = []
    assignment_number = 0
    event_number = 0

    for experiment_id, config in EXPERIMENTS.items():
        for user_number in range(1, users_per_experiment + 1):
            assignment_number += 1

            # User identity is unique per experiment and variant is assigned once.
            user_id = f"{experiment_id}_USER_{user_number:06d}"
            variant = rng.choice(["control", "treatment"])
            device = (
                "mobile"
                if experiment_id == "EXP-025"
                else rng.choice(["mobile", "desktop", "tablet"])
            )
            country = rng.choice(COUNTRIES)
            source = rng.choice(TRAFFIC_SOURCES)
            product_id = rng.choice(PRODUCT_IDS)
            browser = rng.choice(["Chrome", "Safari", "Firefox"])
            os_name = rng.choice(["Windows", "macOS", "Android", "iOS"])
            assigned_at = random_timestamp(rng, config["start"], config["end"])
            session_id = f"{experiment_id}_SESSION_{user_number:06d}"

            # Synthetic probabilities are assumptions, not measured Puffy rates.
            if experiment_id == "EXP-024":
                add_to_cart_probability = (
                    0.38 if variant == "control" else 0.43
                )
                purchase_probability = 0.0
                initial_events = ["session_start", "view_item"]
            else:
                add_to_cart_probability = 1.0
                purchase_probability = (
                    0.28 if variant == "control" else 0.33
                )
                # Assignment occurs at checkout entry; the denominator is users
                # assigned at checkout, represented by begin_checkout events.
                initial_events = ["begin_checkout"]

            sequence = list(initial_events)
            converted = False
            checkout_completed = 0
            revenue = 0.0

            if experiment_id == "EXP-024":
                if rng.random() < add_to_cart_probability:
                    sequence.append("add_to_cart")
                    converted = True
            else:
                if rng.random() < purchase_probability:
                    sequence.append("add_payment_info")
                    sequence.append("purchase")
                    converted = True
                    checkout_completed = 1
                    revenue = float(rng.choice([80, 120, 160, 220, 300]))

            guardrail_refund = int(
                experiment_id == "EXP-025" and converted and rng.random() < 0.03
            )

            assignments.append({
                "assignment_id": f"EXP_ASSIGN_{assignment_number:08d}",
                "experiment_id": experiment_id,
                "user_id": user_id,
                "assignment_timestamp": assigned_at.strftime("%Y-%m-%d %H:%M:%S"),
                "variant": variant,
                "device_category": device,
                "traffic_source": source,
                "country": country,
                "product_id": product_id,
                "eligible": True,
                "converted": int(converted),
                "revenue": revenue,
                "checkout_completed": checkout_completed,
                "guardrail_refund": guardrail_refund,
            })

            event_time = assigned_at
            for event_name in sequence:
                event_number += 1
                events.append(make_event(
                    event_id=f"EXP_EVENT_{event_number:09d}",
                    timestamp=event_time,
                    user_id=user_id,
                    session_id=session_id,
                    event_name=event_name,
                    experiment_id=experiment_id,
                    variant=variant,
                    device=device,
                    country=country,
                    source=source,
                    product_id=product_id,
                    browser=browser,
                    os_name=os_name,
                    rng=rng,
                ))
                event_time += timedelta(seconds=rng.randint(1, 30))

    return assignments, events


def write_csv(path, rows, columns):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(
        description="Generate separate synthetic EXP-024 and EXP-025 datasets."
    )
    parser.add_argument("--users-per-experiment", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    assignments, events = generate_dataset(
        users_per_experiment=args.users_per_experiment,
        seed=args.seed,
    )

    write_csv(
        OUTPUT_DIR / "experiment_assignments.csv",
        assignments,
        ASSIGNMENT_COLUMNS,
    )
    write_csv(
        OUTPUT_DIR / "ga4_experiment_events.csv",
        events,
        EVENT_COLUMNS,
    )

    print("Synthetic experiment dataset generated.")
    print(f"Seed: {args.seed}")
    print(f"Users per experiment: {args.users_per_experiment}")
    print(f"Assignments: {len(assignments):,}")
    print(f"Events: {len(events):,}")
    print(f"Output directory: {OUTPUT_DIR}")
    print("Warning: simulated outcomes are not real Puffy results.")


if __name__ == "__main__":
    main()

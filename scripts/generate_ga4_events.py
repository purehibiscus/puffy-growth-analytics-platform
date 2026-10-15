"""

Features:
- Preserves the existing 20-column GA4 schema.
- Generates coherent, session-based e-commerce journeys.
- Keeps event IDs unique and session attributes consistent.
- Ensures timestamps increase within each session.
- Uses a seeded random generator for reproducibility.
- Writes incrementally to avoid holding the full dataset in memory.
- Never overwrites the original ga4_events.csv by default.

"""

import argparse
import csv
import random
from datetime import datetime, timedelta
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DEFAULT_OUTPUT = (
    PROJECT_ROOT / "data" / "synthetic" / "ga4_events_generated.csv"
)

COLUMNS = [
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

TRAFFIC_SOURCES = [
    ("google", "cpc", "google_brand_search"),
    ("meta", "paid_social", "meta_prospecting"),
    ("organic", "organic", "(none)"),
    ("direct", "(none)", "(none)"),
    ("affiliate", "affiliate", "partner_referral"),
    ("email", "email", "lifecycle_email"),
]

LANDING_PAGES = [
    "/",
    "/collections/mattresses",
    "/collections/pillows",
    "/collections/bedding",
    "/pages/sleep-guide",
]

PRODUCT_PAGES = [
    "/products/mattress",
    "/products/pillow",
    "/products/bed-frame",
    "/products/duvet",
    "/products/mattress-protector",
]

DEVICES = ["mobile", "desktop", "tablet"]
COUNTRIES = ["US", "GB", "CA", "AU"]
BROWSERS = ["Chrome", "Safari", "Firefox", "Edge"]
OPERATING_SYSTEMS = ["Android", "iOS", "Windows", "macOS"]

# Conditional probabilities for a session progressing through the funnel.
ADD_TO_CART_PROBABILITY = 0.50
CHECKOUT_GIVEN_CART_PROBABILITY = 0.65
PAYMENT_GIVEN_CHECKOUT_PROBABILITY = 0.70
PURCHASE_GIVEN_PAYMENT_PROBABILITY = 0.75


def build_session_events(rng):
    """
    Create an ordered event journey for one session.

    Every journey starts with session_start and view_item.
    Purchases can occur only after add_to_cart, begin_checkout,
    and add_payment_info, in that order.
    """
    events = ["session_start", "view_item"]

    # Engagement events occur after the product view.
    if rng.random() < 0.35:
        events.append("scroll_50")

        if rng.random() < 0.55:
            events.append("scroll_90")

    if rng.random() < 0.15:
        events.append("view_reviews")

    if rng.random() < 0.10:
        events.append("click_shipping")

    if rng.random() < 0.08:
        events.append("click_size_guide")

    if rng.random() < 0.05:
        events.append("click_financing")

    # Progress through the purchase funnel conditionally.
    if rng.random() < ADD_TO_CART_PROBABILITY:
        events.append("add_to_cart")

        if rng.random() < CHECKOUT_GIVEN_CART_PROBABILITY:
            events.append("begin_checkout")

            if rng.random() < PAYMENT_GIVEN_CHECKOUT_PROBABILITY:
                events.append("add_payment_info")

                if rng.random() < PURCHASE_GIVEN_PAYMENT_PROBABILITY:
                    events.append("purchase")

    # Only non-purchasing sessions can finish with exit_intent.
    if "purchase" not in events and rng.random() < 0.10:
        events.append("exit_intent")

    return events


def page_for_event(event_name, landing_page, product_page):
    """Return a suitable page location for an event."""
    if event_name == "session_start":
        return landing_page

    if event_name == "view_item":
        return product_page

    if event_name == "add_to_cart":
        return "/cart"

    if event_name in {
        "begin_checkout",
        "add_payment_info",
        "purchase",
    }:
        return "/checkout"

    if event_name in {"scroll_50", "scroll_90"}:
        return product_page

    if event_name == "view_reviews":
        return product_page + "#reviews"

    if event_name == "click_shipping":
        return product_page + "#shipping"

    if event_name == "click_size_guide":
        return product_page + "#size-guide"

    if event_name == "click_financing":
        return product_page + "#financing"

    if event_name == "exit_intent":
        return product_page

    return landing_page


def make_event_row(
    event_id,
    event_timestamp,
    user_id,
    session_id,
    event_name,
    context,
    product_id,
    rng,
):
    """Build a complete event row with no missing field values."""
    if event_name in {"session_start", "view_item"}:
        engagement_seconds = 0
    else:
        engagement_seconds = rng.randint(2, 90)

    if event_name == "scroll_50":
        scroll_depth_pct = 50
    elif event_name == "scroll_90":
        scroll_depth_pct = 90
    elif event_name == "view_item":
        scroll_depth_pct = rng.randint(0, 35)
    else:
        scroll_depth_pct = 0

    return {
        "event_id": event_id,
        "event_timestamp": event_timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        "user_id": user_id,
        "session_id": session_id,
        "event_name": event_name,
        "page_location": page_for_event(
            event_name,
            context["landing_page"],
            context["product_page"],
        ),
        "device_category": context["device_category"],
        "country": context["country"],
        "traffic_source": context["traffic_source"],
        "traffic_medium": context["traffic_medium"],
        "campaign": context["campaign"],
        "landing_page": context["landing_page"],
        "product_id": product_id,
        "experiment_id": context["experiment_id"],
        "experiment_variant": context["experiment_variant"],
        "browser": context["browser"],
        "os": context["os"],
        "engagement_seconds": engagement_seconds,
        "scroll_depth_pct": scroll_depth_pct,
        "page_load_ms": rng.randint(250, 4500),
    }


def generate_events(rows, seed, days, output, chunk_size):
    """Generate exactly the requested number of rows incrementally."""
    rng = random.Random(seed)

    output.parent.mkdir(parents=True, exist_ok=True)

    start_date = datetime(2026, 6, 1)
    date_window_seconds = days * 24 * 60 * 60

    event_counter = 0
    session_counter = 0
    buffer = []

    # Users can appear in multiple sessions, as in normal analytics data.
    user_pool_size = max(1, rows // 8)

    with output.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=COLUMNS,
            extrasaction="raise",
        )
        writer.writeheader()

        while event_counter < rows:
            session_counter += 1

            session_id = f"SES-{session_counter:09d}"
            user_number = rng.randint(1, user_pool_size)
            user_id = f"USR-{user_number:07d}"

            traffic_source, traffic_medium, campaign = rng.choice(
                TRAFFIC_SOURCES
            )
            landing_page = rng.choice(LANDING_PAGES)
            product_page = rng.choice(PRODUCT_PAGES)

            experiment_id = rng.choice(
                ["EXP-001", "EXP-002", "(none)"]
            )

            if experiment_id == "(none)":
                experiment_variant = "(none)"
            else:
                experiment_variant = rng.choice(["control", "treatment"])

            context = {
                "traffic_source": traffic_source,
                "traffic_medium": traffic_medium,
                "campaign": campaign,
                "landing_page": landing_page,
                "product_page": product_page,
                "device_category": rng.choice(DEVICES),
                "country": rng.choice(COUNTRIES),
                "experiment_id": experiment_id,
                "experiment_variant": experiment_variant,
                "browser": rng.choice(BROWSERS),
                "os": rng.choice(OPERATING_SYSTEMS),
            }

            product_number = rng.randint(1, 100)
            product_id = f"PROD-{product_number:04d}"

            # Each session gets its own start time.
            session_start = start_date + timedelta(
                seconds=rng.randrange(date_window_seconds)
            )

            journey = build_session_events(rng)

            # Never exceed the requested total row count.
            remaining_rows = rows - event_counter
            journey = journey[:remaining_rows]

            # One event per session is permitted for a final partial session.
            # Otherwise, journeys start with session_start and view_item.
            previous_timestamp = session_start

            for index, event_name in enumerate(journey):
                if index > 0:
                    previous_timestamp += timedelta(
                        seconds=rng.randint(5, 180)
                    )

                event_counter += 1
                event_id = f"EVT-{event_counter:09d}"

                row = make_event_row(
                    event_id=event_id,
                    event_timestamp=previous_timestamp,
                    user_id=user_id,
                    session_id=session_id,
                    event_name=event_name,
                    context=context,
                    product_id=product_id,
                    rng=rng,
                )

                buffer.append(row)

                if len(buffer) >= chunk_size:
                    writer.writerows(buffer)
                    buffer.clear()

        if buffer:
            writer.writerows(buffer)

    print("Synthetic GA4 generation completed.")
    print(f"Rows requested: {rows:,}")
    print(f"Rows written: {event_counter:,}")
    print(f"Sessions generated: {session_counter:,}")
    print(f"Seed: {seed}")
    print(f"Output: {output.resolve()}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate reproducible synthetic GA4 event data."
    )

    parser.add_argument(
        "--rows",
        type=int,
        default=1000,
        help="Exact number of events to generate (default: 1000).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducibility (default: 42).",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=60,
        help="Number of days covered from 2026-06-01 (default: 60).",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=5000,
        help="Number of rows buffered before writing (default: 5000).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Output CSV path. The original GA4 file is not overwritten.",
    )

    args = parser.parse_args()

    if args.rows < 1:
        parser.error("--rows must be at least 1.")

    if args.days < 1:
        parser.error("--days must be at least 1.")

    if args.chunk_size < 1:
        parser.error("--chunk-size must be at least 1.")

    return args


def main():
    args = parse_args()

    generate_events(
        rows=args.rows,
        seed=args.seed,
        days=args.days,
        output=args.output,
        chunk_size=args.chunk_size,
    )


if __name__ == "__main__":
    main()
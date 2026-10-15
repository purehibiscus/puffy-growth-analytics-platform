
from pathlib import Path
import pandas as pd

path = Path("data/synthetic/ga4_events_corrected_candidate.csv")
df = pd.read_csv(path)
df["event_timestamp"] = pd.to_datetime(
    df["event_timestamp"], utc=True, errors="coerce"
)

# 1. Identity and uniqueness
users_per_session = df.groupby("session_id")["user_id"].nunique()
sessions_with_multiple_users = int((users_per_session > 1).sum())

# 2. Timestamp ordering and session duration
ordered = df.sort_values(
    ["session_id", "event_timestamp", "event_id"]
)
session_stats = ordered.groupby("session_id").agg(
    first_event=("event_timestamp", "min"),
    last_event=("event_timestamp", "max"),
    event_count=("event_id", "size"),
)
session_stats["duration_minutes"] = (
    session_stats["last_event"] - session_stats["first_event"]
).dt.total_seconds() / 60

time_ok = ordered.groupby("session_id")["event_timestamp"].apply(
    lambda s: s.notna().all() and s.is_monotonic_increasing
)

# 3. Funnel-stage ordering within each session
required = [
    "session_start",
    "view_item",
    "add_to_cart",
    "begin_checkout",
    "add_payment_info",
]

invalid_purchases = 0
purchase_sessions = 0

for _, group in ordered.groupby("session_id", sort=False):
    events = group["event_name"].tolist()

    if "purchase" in events:
        purchase_sessions += 1
        purchase_position = events.index("purchase")
        preceding = events[:purchase_position]

        if not all(stage in preceding for stage in required):
            invalid_purchases += 1

# 4. Event distribution
print("FILE:", path)
print("\nIDENTITY")
print("Rows:", len(df))
print("Unique event IDs:", df["event_id"].nunique())
print("Unique sessions:", df["session_id"].nunique())
print("Unique users:", df["user_id"].nunique())
print("Sessions with multiple users:", sessions_with_multiple_users)
print("Null required fields:", int(
    df[["event_id", "user_id", "session_id",
        "event_name", "event_timestamp"]].isna().any(axis=1).sum()
))
print("Duplicate event IDs:", int(df["event_id"].duplicated().sum()))

print("\nTIMESTAMPS AND DURATIONS")
print("Sessions chronologically ordered:", int(time_ok.sum()), "/", len(time_ok))
print("Sessions with timestamp violations:", int((~time_ok).sum()))
print("Sessions <= 30 minutes:", int((session_stats["duration_minutes"] <= 30).sum()))
print("Sessions > 24 hours:", int((session_stats["duration_minutes"] > 1440).sum()))
print("Median duration (minutes):", round(session_stats["duration_minutes"].median(), 2))
print("95th percentile duration (minutes):", round(session_stats["duration_minutes"].quantile(0.95), 2))
print("Maximum duration (minutes):", round(session_stats["duration_minutes"].max(), 2))

print("\nFUNNEL")
print("Sessions with purchase:", purchase_sessions)
print("Purchases missing an earlier required stage:", invalid_purchases)

print("\nEVENT DISTRIBUTION")
print(df["event_name"].value_counts().to_string())

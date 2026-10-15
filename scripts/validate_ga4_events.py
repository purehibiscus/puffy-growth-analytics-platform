import pandas as pd

path = "data/synthetic/ga4_events_generated.csv"
df = pd.read_csv(path)
df["event_timestamp"] = pd.to_datetime(df["event_timestamp"])

# Check chronological timestamps within sessions.
time_ok = df.groupby("session_id")["event_timestamp"].apply(
    lambda values: values.is_monotonic_increasing
)

# Check that purchases have all required earlier funnel stages.
required = [
    "session_start",
    "view_item",
    "add_to_cart",
    "begin_checkout",
    "add_payment_info",
]

invalid_purchases = []

for session_id, group in df.groupby("session_id", sort=False):
    events = group.sort_values("event_timestamp")["event_name"].tolist()

    if "purchase" in events:
        purchase_position = events.index("purchase")
        preceding_events = events[:purchase_position]

        if not all(event in preceding_events for event in required):
            invalid_purchases.append(session_id)

print("Rows:", len(df))
print("Sessions:", df["session_id"].nunique())
print("Sessions with chronological timestamps:", int(time_ok.sum()), "/", len(time_ok))
print("Sessions with timestamp violations:", int((~time_ok).sum()))
print("Purchases missing funnel stages:", len(invalid_purchases))

from pathlib import Path
import pandas as pd

file_path = Path("data/synthetic/ga4_events.csv")

if not file_path.exists():
    raise FileNotFoundError(f"Dataset not found: {file_path}")

rows = 0
event_counts = {}
missing_counts = {}
unique_users = set()
unique_sessions = set()
unique_event_ids = set()
duplicate_ids = 0
min_date = None
max_date = None

for chunk in pd.read_csv(file_path, chunksize=100_000):
    rows += len(chunk)

    event_counts_chunk = chunk["event_name"].value_counts()
    for name, count in event_counts_chunk.items():
        event_counts[name] = event_counts.get(name, 0) + int(count)

    unique_users.update(chunk["user_id"].dropna().astype(str))
    unique_sessions.update(chunk["session_id"].dropna().astype(str))

    event_ids = chunk["event_id"].dropna().astype(str)
    duplicate_ids += int(event_ids.duplicated().sum())
    unique_event_ids.update(event_ids)

    timestamps = pd.to_datetime(
        chunk["event_timestamp"], errors="coerce"
    )
    chunk_min = timestamps.min()
    chunk_max = timestamps.max()

    if pd.notna(chunk_min):
        min_date = chunk_min if min_date is None else min(min_date, chunk_min)

    if pd.notna(chunk_max):
        max_date = chunk_max if max_date is None else max(max_date, chunk_max)

    for column, count in chunk.isna().sum().items():
        missing_counts[column] = missing_counts.get(column, 0) + int(count)

print("\n=== GA4 DATASET PROFILE ===")
print(f"File size: {file_path.stat().st_size / 1024**2:.2f} MB")
print(f"Total rows: {rows:,}")
print(f"Unique event IDs: {len(unique_event_ids):,}")
print(f"Duplicate IDs within individual chunks: {duplicate_ids:,}")
print(f"Unique users: {len(unique_users):,}")
print(f"Unique sessions: {len(unique_sessions):,}")
print(f"Date range: {min_date} to {max_date}")

print("\n=== EVENT COUNTS ===")
print(pd.Series(event_counts).sort_values(ascending=False).to_string())

print("\n=== MISSING VALUES ===")
print(pd.Series(missing_counts).sort_values(ascending=False).to_string())

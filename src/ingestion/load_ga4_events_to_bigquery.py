
import os
from pathlib import Path

from google.cloud import bigquery
from google.oauth2 import service_account

PROJECT_ID = "puffy-platform"
DATASET_ID = "growthanalytics"
TABLE_ID = "raw_ga4_events"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CSV_PATH = PROJECT_ROOT / "data" / "synthetic" / "ga4_events.csv"


def main():
    keyfile = os.environ.get("DBT_GOOGLE_KEYFILE")

    if not keyfile:
        raise EnvironmentError(
            "DBT_GOOGLE_KEYFILE is not set."
        )

    if not Path(keyfile).is_file():
        raise FileNotFoundError(
            f"Service-account key file not found: {keyfile}"
        )

    if not CSV_PATH.is_file():
        raise FileNotFoundError(
            f"GA4 CSV not found: {CSV_PATH}"
        )

    credentials = service_account.Credentials.from_service_account_file(
        keyfile
    )

    client = bigquery.Client(
        project=PROJECT_ID,
        credentials=credentials,
    )

    table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"

    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.CSV,
        skip_leading_rows=1,
        autodetect=True,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
    )

    print(f"Source: {CSV_PATH}")
    print(f"Destination: {table_ref}")
    print("Starting BigQuery load...")

    with CSV_PATH.open("rb") as csv_file:
        job = client.load_table_from_file(
            csv_file,
            table_ref,
            job_config=job_config,
        )

    job.result()

    table = client.get_table(table_ref)

    print("\nGA4 load completed successfully.")
    print(f"Table: {table.full_table_id}")
    print(f"Rows loaded: {table.num_rows:,}")
    print(f"Columns detected: {len(table.schema)}")

    print("\nDetected schema:")
    for field in table.schema:
        print(f"  {field.name}: {field.field_type} ({field.mode})")


if __name__ == "__main__":
    main()

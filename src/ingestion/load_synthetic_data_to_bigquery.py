
import os
from pathlib import Path
from google.cloud import bigquery


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "synthetic"

PROJECT_ID = "puffy-platform"
DATASET_ID = "growthanalytics"

TABLES = {
    "products.csv": "raw_products",
    "customers.csv": "raw_customers",
    "shopify_orders.csv": "raw_shopify_orders",
    "shopify_order_items.csv": "raw_shopify_order_items",
}


def main():
    keyfile = os.environ.get("DBT_GOOGLE_KEYFILE")
    if not keyfile or not Path(keyfile).is_file():
        raise RuntimeError(
            "DBT_GOOGLE_KEYFILE is missing or points to a nonexistent file."
        )

    client = bigquery.Client.from_service_account_json(
        keyfile, project=PROJECT_ID
    )

    dataset_ref = bigquery.Dataset(
        f"{PROJECT_ID}.{DATASET_ID}"
    )
    dataset_ref.location = "US"
    client.create_dataset(dataset_ref, exists_ok=True)

    for filename, table_name in TABLES.items():
        csv_path = DATA_DIR / filename
        if not csv_path.is_file():
            raise FileNotFoundError(f"CSV not found: {csv_path}")

        table_id = f"{PROJECT_ID}.{DATASET_ID}.{table_name}"
        print(f"\nLoading {filename} into {table_id}...")

        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.CSV,
            skip_leading_rows=1,
            autodetect=True,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        )

        with csv_path.open("rb") as source_file:
            job = client.load_table_from_file(
                source_file,
                table_id,
                job_config=job_config,
            )

        job.result()
        table = client.get_table(table_id)
        print(f"Loaded rows: {table.num_rows:,}")

    print("\nAll four CSV files loaded successfully.")


if __name__ == "__main__":
    main()

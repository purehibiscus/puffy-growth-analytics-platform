
import argparse
import hashlib
import json
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from src.ingestion.shopify_products import get_access_token, graphql_request


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_FILE = PROJECT_ROOT / "data" / "synthetic" / "products.csv"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"

LOCATION_ID = "gid://shopify/Location/113689297212"
API_PAGE_SIZE = 100


def fetch_shopify_products(access_token):
    """Fetch all Shopify products and their location-specific inventory."""
    products = []
    cursor = None

    while True:
        after = (
            f', after: "{cursor}"'
            if cursor
            else ""
        )

        query = f"""
        query {{
          products(first: {API_PAGE_SIZE}{after}) {{
            nodes {{
              id
              title
              variants(first: 100) {{
                nodes {{
                  id
                  sku
                  inventoryItem {{
                    id
                    tracked
                    inventoryLevel(locationId: "{LOCATION_ID}") {{
                      quantities(names: ["available"]) {{
                        name
                        quantity
                      }}
                    }}
                  }}
                }}
              }}
            }}
            pageInfo {{
              hasNextPage
              endCursor
            }}
          }}
        }}
        """

        response = graphql_request(access_token, query)
        connection = response["data"]["products"]

        for product in connection["nodes"]:
            for variant in product["variants"]["nodes"]:
                inventory_item = variant.get("inventoryItem") or {}
                inventory_level = inventory_item.get("inventoryLevel")

                available = None
                if inventory_level:
                    for quantity in inventory_level.get("quantities", []):
                        if quantity["name"] == "available":
                            available = int(quantity["quantity"])
                            break

                products.append({
                    "shopify_product_id": product["id"],
                    "shopify_product_title": product["title"],
                    "shopify_variant_id": variant["id"],
                    "sku": (variant.get("sku") or "").strip(),
                    "inventory_item_id": inventory_item.get("id"),
                    "tracked": inventory_item.get("tracked"),
                    "shopify_available_qty": available,
                })

        page_info = connection["pageInfo"]
        if not page_info["hasNextPage"]:
            break

        cursor = page_info["endCursor"]

    return pd.DataFrame(products)


def build_reconciliation(source, shopify):
    """Match products by SKU and flag unsafe or inconsistent records."""
    source = source.copy()
    shopify = shopify.copy()

    source["sku"] = source["sku"].fillna("").astype(str).str.strip()
    source["inventory_qty"] = pd.to_numeric(
        source["inventory_qty"], errors="raise"
    ).astype(int)

    if (source["inventory_qty"] < 0).any():
        raise ValueError("Source contains negative inventory quantities.")

    if source["sku"].eq("").any():
        raise ValueError("Source contains missing or blank SKUs.")

    if source["sku"].duplicated().any():
        duplicates = source.loc[
            source["sku"].duplicated(keep=False), "sku"
        ].tolist()
        raise ValueError(f"Duplicate source SKUs: {duplicates}")

    shopify["sku"] = shopify["sku"].fillna("").astype(str).str.strip()

    nonblank = shopify[shopify["sku"] != ""]
    duplicate_shopify = set(
        nonblank.loc[
            nonblank["sku"].duplicated(keep=False), "sku"
        ]
    )

    rows = []

    for _, source_row in source.iterrows():
        sku = source_row["sku"]
        matches = nonblank[nonblank["sku"] == sku]
        source_qty = int(source_row["inventory_qty"])

        record = {
            "sku": sku,
            "product_name": source_row.get("product_name", ""),
            "source_inventory_qty": source_qty,
            "shopify_product_id": "",
            "shopify_product_title": "",
            "shopify_variant_id": "",
            "inventory_item_id": "",
            "shopify_available_qty": None,
            "quantity_difference": None,
            "status": "",
        }

        if sku in duplicate_shopify:
            record["status"] = "DUPLICATE_SHOPIFY_SKU"

        elif matches.empty:
            record["status"] = "MISSING_IN_SHOPIFY"

        else:
            item = matches.iloc[0]
            record.update({
                "shopify_product_id": item["shopify_product_id"],
                "shopify_product_title": item["shopify_product_title"],
                "shopify_variant_id": item["shopify_variant_id"],
                "inventory_item_id": item["inventory_item_id"] or "",
                "shopify_available_qty": item["shopify_available_qty"],
            })

            if not item["inventory_item_id"]:
                record["status"] = "MISSING_INVENTORY_ITEM"

            elif pd.isna(item["tracked"]) or not bool(item["tracked"]):
                record["status"] = "INVENTORY_NOT_TRACKED"

            elif pd.isna(item["shopify_available_qty"]):
                record["status"] = "NO_INVENTORY_LEVEL_AT_LOCATION"

            else:
                current_qty = int(item["shopify_available_qty"])
                difference = source_qty - current_qty
                record["quantity_difference"] = difference
                record["status"] = (
                    "MATCH"
                    if difference == 0
                    else "MISMATCH"
                )

        rows.append(record)

    return pd.DataFrame(rows)


def set_inventory(access_token, row, run_id):
    """Set one quantity using a compare-and-set safety check."""
    sku = row["sku"]
    current_qty = int(row["shopify_available_qty"])
    target_qty = int(row["source_inventory_qty"])
    inventory_item_id = row["inventory_item_id"]

    # A unique key per SKU and execution; safe to reuse if this same
    # request needs to be retried after an uncertain network result.
    key_source = f"{run_id}|{sku}|{current_qty}|{target_qty}"
    idempotency_key = hashlib.sha256(
        key_source.encode("utf-8")
    ).hexdigest()

    safe_sku = sku.replace("/", "-")
    reference_uri = (
        "logistics://puffy-growth-analytics-platform/"
        f"inventory-sync/{safe_sku}/{run_id}"
    )

    query = f"""
    mutation {{
      inventorySetQuantities(
        input: {{
          name: "available"
          reason: "correction"
          referenceDocumentUri: "{reference_uri}"
          quantities: [{{
            inventoryItemId: "{inventory_item_id}"
            locationId: "{LOCATION_ID}"
            quantity: {target_qty}
            changeFromQuantity: {current_qty}
          }}]
        }}
      ) @idempotent(key: "{idempotency_key}") {{
        inventoryAdjustmentGroup {{
          createdAt
          reason
          changes {{
            name
            delta
            quantityAfterChange
          }}
        }}
        userErrors {{
          field
          message
        }}
      }}
    }}
    """

    response = graphql_request(access_token, query)
    result = (response.get("data") or {}).get(
        "inventorySetQuantities"
    )

    if not isinstance(result, dict):
        return "UPDATE_FAILED: Missing mutation result."

    errors = result.get("userErrors") or []
    if errors:
        return "UPDATE_REJECTED: " + json.dumps(errors)

    adjustment_group = result.get("inventoryAdjustmentGroup")
    if not isinstance(adjustment_group, dict):
        return "UPDATE_FAILED: Missing inventory adjustment group."

    return "UPDATED"

def append_audit_log(run_id, row, outcome):
    audit_path = OUTPUT_DIR / "inventory_audit_log.csv"
    audit_path.parent.mkdir(parents=True, exist_ok=True)

    file_exists = audit_path.exists()

    record = {
        "run_id": run_id,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "sku": row.get("sku", ""),
        "inventory_item_id": row.get("inventory_item_id", ""),
        "original_quantity": row.get("shopify_available_qty", ""),
        "target_quantity": row.get("inventory_qty", ""),
        "quantity_delta": (
            row.get("inventory_qty", 0)
            - row.get("shopify_available_qty", 0)
            if pd.notna(row.get("inventory_qty"))
            and pd.notna(row.get("shopify_available_qty"))
            else ""
        ),
        "outcome": outcome,
    }

    with open(audit_path, "a", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=record.keys())

        if not file_exists:
            writer.writeheader()

        writer.writerow(record)
def main():
    parser = argparse.ArgumentParser(
        description="Reconcile Shopify inventory against the synthetic CSV."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply eligible inventory changes. Default is dry-run.",
    )
    args = parser.parse_args()

    if not SOURCE_FILE.exists():
        sys.exit(f"Source file not found: {SOURCE_FILE}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    source = pd.read_csv(SOURCE_FILE)
    required = {"sku", "inventory_qty"}
    missing_columns = required - set(source.columns)

    if missing_columns:
        sys.exit(f"Missing required source columns: {sorted(missing_columns)}")

    print("Authenticating with Shopify...")
    access_token = get_access_token()

    print("Fetching Shopify products and location inventory...")
    shopify = fetch_shopify_products(access_token)

    print(f"Source products: {len(source)}")
    print(f"Shopify variants fetched: {len(shopify)}")

    report = build_reconciliation(source, shopify)

    matches = int((report["status"] == "MATCH").sum())
    mismatches = int((report["status"] == "MISMATCH").sum())
    exceptions = len(report) - matches - mismatches

    print("\nReconciliation summary")
    print(f"Already matching: {matches}")
    print(f"Quantity mismatches: {mismatches}")
    print(f"Exceptions requiring review: {exceptions}")

    if args.apply:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        eligible = report.index[report["status"] == "MISMATCH"].tolist()

        print(f"\nAPPLY MODE: processing {len(eligible)} mismatches.")


        for index in eligible:
            row = report.loc[index]

            try:
                outcome = set_inventory(access_token, row, run_id)
                report.loc[index, "status"] = outcome
                append_audit_log(run_id, row, outcome)
                print(f"{row['sku']}: {outcome}")

            except Exception as exc:
                outcome = "ERROR: " + str(exc)
                report.loc[index, "status"] = outcome
                append_audit_log(run_id, row, outcome)
                print(f"{row['sku']}: {outcome}")

    else:
        print("\nDRY RUN: no inventory changes were requested.")
        print("Review the report before using --apply.")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_path = OUTPUT_DIR / f"inventory_reconciliation_{timestamp}.csv"
    report.to_csv(report_path, index=False)

    print(f"\nReport saved to: {report_path}")

    print("\nStatus breakdown:")
    print(report["status"].value_counts(dropna=False).to_string())


if __name__ == "__main__":
    main()

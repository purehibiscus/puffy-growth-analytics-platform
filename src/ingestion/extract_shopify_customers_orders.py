
"""Read-only Shopify customer and order extractor.

Uses the existing Shopify authentication and GraphQL helpers.
Writes timestamped CSVs to data/processed; never writes to Shopify or BigQuery.
"""

from datetime import datetime, timezone
from pathlib import Path
import sys

import pandas as pd

from src.ingestion.shopify_products import (
    PROJECT_ROOT,
    get_access_token,
    graphql_request,
)

OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
PAGE_SIZE = 100


def paginate(query, root_key, access_token, node_mapper):
    """Fetch all pages and map each returned node."""
    records = []
    cursor = None

    while True:
        data = graphql_request(
            access_token,
            query,
            {"first": PAGE_SIZE, "after": cursor},
        )
        connection = data.get("data", {}).get(root_key)

        if connection is None:
            raise RuntimeError(
                f"Shopify response did not contain '{root_key}'."
            )

        records.extend(node_mapper(node) for node in connection["nodes"])
        page_info = connection["pageInfo"]

        if not page_info["hasNextPage"]:
            break

        cursor = page_info["endCursor"]
        if not cursor:
            raise RuntimeError("Pagination cursor missing; stopping safely.")

    return records


CUSTOMERS_QUERY = """
query Customers($first: Int!, $after: String) {
  customers(first: $first, after: $after) {
    nodes {
      id
      createdAt
      numberOfOrders
      amountSpent {
        amount
        currencyCode
      }
      defaultAddress {
        countryCodeV2
      }
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
"""

ORDERS_QUERY = """
query Orders($first: Int!, $after: String) {
  orders(first: $first, after: $after, sortKey: CREATED_AT) {
    nodes {
      id
      name
      createdAt
      updatedAt
      displayFinancialStatus
      displayFulfillmentStatus
      currencyCode
      subtotalPriceSet {
        shopMoney {
          amount
          currencyCode
        }
      }
      totalDiscountsSet {
        shopMoney {
          amount
          currencyCode
        }
      }
      totalShippingPriceSet {
        shopMoney {
          amount
          currencyCode
        }
      }
      totalTaxSet {
        shopMoney {
          amount
          currencyCode
        }
      }
      totalRefundedSet {
        shopMoney {
          amount
          currencyCode
        }
      }
      currentTotalPriceSet {
        shopMoney {
          amount
          currencyCode
        }
      }
      customer {
        id
      }
      shippingAddress {
        countryCodeV2
      }
      sourceName
    }
    pageInfo {
      hasNextPage
      endCursor
    }
  }
}
"""


def money_value(container, field):
    money = (container.get(field) or {}).get("shopMoney") or {}
    return money.get("amount")


def customer_row(node):
    spent = node.get("amountSpent") or {}
    address = node.get("defaultAddress") or {}

    return {
        "shopify_customer_id": node.get("id"),
        "created_at": node.get("createdAt"),
        "lifetime_orders_reported_by_shopify": node.get("numberOfOrders"),
        "lifetime_spend_reported_by_shopify": spent.get("amount"),
        "currency": spent.get("currencyCode"),
        "country": address.get("countryCodeV2"),
    }


def order_row(node):
    customer = node.get("customer") or {}
    address = node.get("shippingAddress") or {}

    return {
        "shopify_order_id": node.get("id"),
        "order_name": node.get("name"),
        "created_at": node.get("createdAt"),
        "updated_at": node.get("updatedAt"),
        "financial_status": node.get("displayFinancialStatus"),
        "fulfillment_status": node.get("displayFulfillmentStatus"),
        "currency": node.get("currencyCode"),
        "subtotal": money_value(node, "subtotalPriceSet"),
        "discounts": money_value(node, "totalDiscountsSet"),
        "shipping": money_value(node, "totalShippingPriceSet"),
        "tax": money_value(node, "totalTaxSet"),
        "total_refunded": money_value(node, "totalRefundedSet"),
        "current_total": money_value(node, "currentTotalPriceSet"),
        "shopify_customer_id": customer.get("id"),
        "shipping_country": address.get("countryCodeV2"),
        "source_name": node.get("sourceName"),
    }


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    token = get_access_token()

    print("Reading customers from Shopify...")
    customers = paginate(
        CUSTOMERS_QUERY, "customers", token, customer_row
    )

    print("Reading orders from Shopify...")
    orders = paginate(ORDERS_QUERY, "orders", token, order_row)

    # Never overwrite prior extraction files.
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outputs = {
        "customers": (customers, OUTPUT_DIR / f"shopify_customers_{stamp}.csv"),
        "orders": (orders, OUTPUT_DIR / f"shopify_orders_{stamp}.csv"),
    }

    for label, (records, path) in outputs.items():
        if records:
            if path.exists():
                raise FileExistsError(f"Refusing to overwrite: {path.name}")
            pd.DataFrame(records).to_csv(path, index=False)
            print(f"{label.title()}: {len(records)} rows -> {path.name}")
        else:
            print(f"{label.title()}: 0 rows; no CSV created.")

    print("Extraction finished. Shopify and BigQuery were not modified.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Extraction failed: {type(exc).__name__}: {exc}")
        sys.exit(1)

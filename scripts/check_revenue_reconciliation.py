
from pathlib import Path
import sys

import pandas as pd

# Resolve the project root so the script works regardless of
# the directory from which it is executed.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.ingestion.reconcile_revenue import build_revenue_reconciliation

# Project directories
DATA_DIR = PROJECT_ROOT / "data" / "synthetic"
OUTPUT_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def main():
    # Load synthetic Shopify data.
    orders = pd.read_csv(DATA_DIR / "shopify_orders.csv")
    items = pd.read_csv(DATA_DIR / "shopify_order_items.csv")

    # Build order-level revenue reconciliation.
    report = build_revenue_reconciliation(orders, items)

    # Detailed, order-level audit report.
    detail_columns = [
        "order_id",
        "order_status",
        "subtotal",
        "discount",
        "shipping",
        "tax",
        "refund_amount",
        "net_revenue",
        "item_revenue",
        "expected_item_revenue",
        "item_revenue_difference",
        "expected_net_revenue",
        "net_revenue_difference",
        "has_items",
        "item_revenue_matches",
        "net_revenue_matches",
    ]

    detail_path = OUTPUT_DIR / "revenue_reconciliation.csv"
    report[detail_columns].to_csv(detail_path, index=False)

    # Status-level summary.
    summary = (
        report.groupby("order_status")
        .agg(
            order_count=("order_id", "size"),
            net_revenue=("net_revenue", "sum"),
            refunds=("refund_amount", "sum"),
            orders_without_items=("has_items", lambda s: (~s).sum()),
            item_revenue_mismatches=(
                "item_revenue_matches",
                lambda s: (~s).sum(),
            ),
            net_revenue_mismatches=(
                "net_revenue_matches",
                lambda s: (~s).sum(),
            ),
        )
        .reset_index()
    )

    summary_path = OUTPUT_DIR / "revenue_reconciliation_summary.csv"
    summary.to_csv(summary_path, index=False)

    # Print reconciliation results.
    print("Revenue reconciliation completed.")
    print("Orders analyzed:", len(report))
    print("Orders without items:", int((~report["has_items"]).sum()))
    print(
        "Item revenue mismatches:",
        int((~report["item_revenue_matches"]).sum()),
    )
    print(
        "Net revenue mismatches:",
        int((~report["net_revenue_matches"]).sum()),
    )

    print("\nStatus summary:")
    print(summary.to_string(index=False))

    print("\nReports saved:")
    print(detail_path)
    print(summary_path)


if __name__ == "__main__":
    main()

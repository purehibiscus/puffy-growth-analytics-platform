
import pandas as pd


def build_revenue_reconciliation(
    orders: pd.DataFrame,
    items: pd.DataFrame,
    tolerance: float = 0.02,
) -> pd.DataFrame:
    """Compare item totals and net revenue with the verified synthetic rules."""
    required_orders = {
        "order_id", "order_status", "subtotal", "discount",
        "shipping", "tax", "refund_amount", "net_revenue",
    }
    required_items = {"order_id", "line_revenue"}

    missing_orders = required_orders - set(orders.columns)
    missing_items = required_items - set(items.columns)

    if missing_orders:
        raise ValueError(
            f"Missing order columns: {', '.join(sorted(missing_orders))}"
        )
    if missing_items:
        raise ValueError(
            f"Missing item columns: {', '.join(sorted(missing_items))}"
        )
    if tolerance <= 0:
        raise ValueError("tolerance must be greater than zero")

    item_totals = (
        items.groupby("order_id")["line_revenue"]
        .sum()
        .rename("item_revenue")
    )

    result = orders.join(item_totals, on="order_id")
    result["has_items"] = result["item_revenue"].notna()

    result["expected_item_revenue"] = (
        result["subtotal"] - result["discount"]
    )
    result["item_revenue_difference"] = (
        result["item_revenue"] - result["expected_item_revenue"]
    )

    result["expected_net_revenue"] = (
        result["subtotal"]
        - result["discount"]
        + result["shipping"]
        + result["tax"]
        - result["refund_amount"]
    )
    result["net_revenue_difference"] = (
        result["net_revenue"] - result["expected_net_revenue"]
    )

    result["item_revenue_matches"] = (
        result["has_items"]
        & (result["item_revenue_difference"].abs() < tolerance)
    )
    result["net_revenue_matches"] = (
        result["net_revenue_difference"].abs() < tolerance
    )

    return result

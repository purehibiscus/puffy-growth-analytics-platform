
import pandas as pd


ORDER_COLUMNS = {
    "order_id", "customer_id", "order_timestamp", "order_status",
    "subtotal", "discount", "shipping", "tax", "refund_amount",
    "net_revenue", "currency", "payment_method", "shipping_country",
    "device_category", "landing_page", "traffic_source", "traffic_medium",
    "campaign", "coupon_code", "shipping_method", "fulfillment_status",
}

ITEM_COLUMNS = {
    "order_item_id", "order_id", "product_id", "quantity",
    "unit_price", "discount", "line_revenue", "gross_margin",
}

ORDER_STATUSES = {
    "paid", "fulfilled", "partially_refunded", "refunded", "cancelled",
}

FULFILLMENT_STATUSES = {
    "fulfilled", "delivered", "processing", "cancelled",
}


def validate_order_data(
    orders: pd.DataFrame,
    items: pd.DataFrame,
    customers: pd.DataFrame,
    products: pd.DataFrame,
) -> list[str]:
    """Validate order and order-item data without modifying any inputs."""
    errors = []

    missing_order_columns = ORDER_COLUMNS - set(orders.columns)
    missing_item_columns = ITEM_COLUMNS - set(items.columns)

    if missing_order_columns:
        errors.append(
            "Missing order columns: "
            + ", ".join(sorted(missing_order_columns))
        )

    if missing_item_columns:
        errors.append(
            "Missing order-item columns: "
            + ", ".join(sorted(missing_item_columns))
        )

    if missing_order_columns or missing_item_columns:
        return errors

    # IDs must exist and be unique within their respective tables.
    for df, column, label in [
        (orders, "order_id", "order_id"),
        (items, "order_item_id", "order_item_id"),
    ]:
        if df[column].isna().any():
            errors.append(f"{label} contains missing values")
        elif df[column].astype(str).str.strip().eq("").any():
            errors.append(f"{label} contains blank values")
        elif df[column].duplicated().any():
            errors.append(f"{label} contains duplicate values")

    # Required relationships.
    for df, column, label in [
        (orders, "customer_id", "customer_id"),
        (items, "order_id", "order_id"),
        (items, "product_id", "product_id"),
    ]:
        if df[column].isna().any():
            errors.append(f"{label} contains missing values")

    if not orders["customer_id"].isin(customers["customer_id"]).all():
        errors.append("Orders reference unknown customers")

    if not items["order_id"].isin(orders["order_id"]).all():
        errors.append("Order items reference unknown orders")

    if not items["product_id"].isin(products["product_id"]).all():
        errors.append("Order items reference unknown products")

    # Timestamps must parse successfully.
    timestamps = pd.to_datetime(orders["order_timestamp"], errors="coerce")
    if timestamps.isna().any():
        errors.append("order_timestamp contains invalid or missing dates")

    # Validate known status categories.
    if not orders["order_status"].isin(ORDER_STATUSES).all():
        errors.append("order_status contains unknown or missing statuses")

    if not orders["fulfillment_status"].isin(
        FULFILLMENT_STATUSES
    ).all():
        errors.append(
            "fulfillment_status contains unknown or missing statuses"
        )

    # Financial amounts must be numeric and non-negative.
    order_amounts = [
        "subtotal", "discount", "shipping", "tax",
        "refund_amount", "net_revenue",
    ]
    for column in order_amounts:
        values = pd.to_numeric(orders[column], errors="coerce")
        if values.isna().any():
            errors.append(f"{column} contains non-numeric or missing values")
        elif (values < 0).any():
            errors.append(f"{column} contains negative values")

    item_amounts = ["unit_price", "discount", "line_revenue", "gross_margin"]
    for column in item_amounts:
        values = pd.to_numeric(items[column], errors="coerce")
        if values.isna().any():
            errors.append(f"{column} contains non-numeric or missing values")

    # Quantities must be numeric and strictly positive.
    quantities = pd.to_numeric(items["quantity"], errors="coerce")
    if quantities.isna().any():
        errors.append("quantity contains non-numeric or missing values")
    elif (quantities <= 0).any():
        errors.append("quantity contains zero or negative values")

    return errors

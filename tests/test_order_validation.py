
import pandas as pd

from src.ingestion.validate_orders import validate_order_data


def sample_data():
    customers = pd.DataFrame([
        {"customer_id": "CUST-001"},
    ])
    products = pd.DataFrame([
        {"product_id": "PROD-001"},
    ])
    orders = pd.DataFrame([{
        "order_id": "ORD-001",
        "customer_id": "CUST-001",
        "order_timestamp": "2026-02-21 10:00:00",
        "order_status": "paid",
        "subtotal": 100.0,
        "discount": 5.0,
        "shipping": 10.0,
        "tax": 8.0,
        "refund_amount": 0.0,
        "net_revenue": 95.0,
        "currency": "USD",
        "payment_method": "card",
        "shipping_country": "US",
        "device_category": "desktop",
        "landing_page": "/",
        "traffic_source": "google",
        "traffic_medium": "organic",
        "campaign": None,
        "coupon_code": None,
        "shipping_method": "standard",
        "fulfillment_status": "processing",
    }])
    items = pd.DataFrame([{
        "order_item_id": "ITEM-001",
        "order_id": "ORD-001",
        "product_id": "PROD-001",
        "quantity": 1,
        "unit_price": 100.0,
        "discount": 5.0,
        "line_revenue": 95.0,
        "gross_margin": 40.0,
    }])
    return orders, items, customers, products


def test_valid_order_data_passes():
    assert validate_order_data(*sample_data()) == []


def test_duplicate_order_id_fails():
    orders, items, customers, products = sample_data()
    orders = pd.concat([orders, orders], ignore_index=True)
    errors = validate_order_data(orders, items, customers, products)
    assert any("order_id contains duplicate" in e for e in errors)


def test_duplicate_order_item_id_fails():
    orders, items, customers, products = sample_data()
    items = pd.concat([items, items], ignore_index=True)
    errors = validate_order_data(orders, items, customers, products)
    assert any("order_item_id contains duplicate" in e for e in errors)


def test_unknown_customer_fails():
    orders, items, customers, products = sample_data()
    orders.loc[0, "customer_id"] = "CUST-UNKNOWN"
    errors = validate_order_data(orders, items, customers, products)
    assert any("unknown customers" in e for e in errors)


def test_unknown_order_reference_fails():
    orders, items, customers, products = sample_data()
    items.loc[0, "order_id"] = "ORD-UNKNOWN"
    errors = validate_order_data(orders, items, customers, products)
    assert any("unknown orders" in e for e in errors)


def test_unknown_product_fails():
    orders, items, customers, products = sample_data()
    items.loc[0, "product_id"] = "PROD-UNKNOWN"
    errors = validate_order_data(orders, items, customers, products)
    assert any("unknown products" in e for e in errors)


def test_invalid_timestamp_fails():
    orders, items, customers, products = sample_data()
    orders.loc[0, "order_timestamp"] = "not-a-date"
    errors = validate_order_data(orders, items, customers, products)
    assert any("invalid or missing dates" in e for e in errors)


def test_negative_order_amount_fails():
    orders, items, customers, products = sample_data()
    orders.loc[0, "subtotal"] = -10
    errors = validate_order_data(orders, items, customers, products)
    assert any("subtotal contains negative" in e for e in errors)


def test_zero_quantity_fails():
    orders, items, customers, products = sample_data()
    items.loc[0, "quantity"] = 0
    errors = validate_order_data(orders, items, customers, products)
    assert any("quantity contains zero or negative" in e for e in errors)


def test_missing_required_column_fails():
    orders, items, customers, products = sample_data()
    orders = orders.drop(columns=["currency"])
    errors = validate_order_data(orders, items, customers, products)
    assert any("Missing order columns" in e for e in errors)


def test_negative_gross_margin_is_allowed():
    orders, items, customers, products = sample_data()
    items.loc[0, "gross_margin"] = -5
    assert validate_order_data(orders, items, customers, products) == []

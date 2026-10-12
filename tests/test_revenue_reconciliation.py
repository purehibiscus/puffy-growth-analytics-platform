
import pandas as pd
import pytest

from src.ingestion.reconcile_revenue import build_revenue_reconciliation


def sample_data():
    orders = pd.DataFrame([{
        "order_id": "ORD-001",
        "order_status": "paid",
        "subtotal": 100.00,
        "discount": 5.00,
        "shipping": 10.00,
        "tax": 8.00,
        "refund_amount": 0.00,
        "net_revenue": 113.00,
    }])
    items = pd.DataFrame([{
        "order_id": "ORD-001",
        "line_revenue": 95.00,
    }])
    return orders, items


def test_valid_revenue_matches_both_rules():
    orders, items = sample_data()
    result = build_revenue_reconciliation(orders, items)

    assert result.loc[0, "item_revenue_matches"]
    assert result.loc[0, "net_revenue_matches"]
    assert result.loc[0, "net_revenue_difference"] == 0


def test_item_revenue_mismatch_is_flagged():
    orders, items = sample_data()
    items.loc[0, "line_revenue"] = 90.00

    result = build_revenue_reconciliation(orders, items)

    assert not result.loc[0, "item_revenue_matches"]


def test_net_revenue_mismatch_is_flagged():
    orders, items = sample_data()
    orders.loc[0, "net_revenue"] = 100.00

    result = build_revenue_reconciliation(orders, items)

    assert not result.loc[0, "net_revenue_matches"]


def test_order_without_items_is_flagged():
    orders, items = sample_data()
    items = items.iloc[0:0]

    result = build_revenue_reconciliation(orders, items)

    assert not result.loc[0, "has_items"]
    assert not result.loc[0, "item_revenue_matches"]


def test_tolerance_must_be_positive():
    orders, items = sample_data()

    with pytest.raises(ValueError, match="greater than zero"):
        build_revenue_reconciliation(orders, items, tolerance=0)

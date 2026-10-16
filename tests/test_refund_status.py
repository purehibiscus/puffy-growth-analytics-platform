
import pandas as pd

from src.ingestion.validate_refund_status import validate_refund_status


def test_refunded_order_with_positive_net_revenue_is_flagged():
    orders = pd.DataFrame([{
        "order_id": "ORD-001",
        "order_status": "refunded",
        "refund_amount": 0.00,
        "net_revenue": 100.00,
    }])

    result = validate_refund_status(orders)

    assert result.loc[0, "refund_status_issue"]
    assert "positive net revenue" in result.loc[0, "refund_status_issue_reason"]


def test_cancelled_order_with_positive_net_revenue_is_flagged():
    orders = pd.DataFrame([{
        "order_id": "ORD-002",
        "order_status": "cancelled",
        "refund_amount": 0.00,
        "net_revenue": 75.00,
    }])

    result = validate_refund_status(orders)

    assert result.loc[0, "refund_status_issue"]


def test_partially_refunded_order_without_refund_is_flagged():
    orders = pd.DataFrame([{
        "order_id": "ORD-003",
        "order_status": "partially_refunded",
        "refund_amount": 0.00,
        "net_revenue": 50.00,
    }])

    result = validate_refund_status(orders)

    assert result.loc[0, "refund_status_issue"]


def test_paid_order_with_zero_refund_is_not_flagged():
    orders = pd.DataFrame([{
        "order_id": "ORD-004",
        "order_status": "paid",
        "refund_amount": 0.00,
        "net_revenue": 100.00,
    }])

    result = validate_refund_status(orders)

    assert not result.loc[0, "refund_status_issue"]


def test_input_orders_are_not_modified():
    orders = pd.DataFrame([{
        "order_id": "ORD-005",
        "order_status": "paid",
        "refund_amount": 0.00,
        "net_revenue": 100.00,
    }])
    original = orders.copy(deep=True)

    validate_refund_status(orders)

    pd.testing.assert_frame_equal(orders, original)

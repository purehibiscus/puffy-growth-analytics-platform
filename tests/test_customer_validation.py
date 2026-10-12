
import pandas as pd

from src.ingestion.validate_customers import validate_customer_data


def valid_customer():
    return pd.DataFrame([{
        "customer_id": "CUST-001",
        "customer_email_hash": "hash-001",
        "customer_type": "new",
        "country": "US",
        "acquisition_source": "google",
        "first_purchase_date": "2026-02-21",
        "lifetime_orders": 2,
        "lifetime_revenue": 120.50,
        "marketing_opt_in": True,
        "loyalty_tier": None,
    }])


def test_valid_customer_allows_missing_loyalty_tier():
    assert validate_customer_data(valid_customer()) == []


def test_duplicate_customer_id_is_rejected():
    df = pd.concat([valid_customer(), valid_customer()], ignore_index=True)
    errors = validate_customer_data(df)
    assert any("customer_id contains duplicate" in e for e in errors)


def test_missing_customer_id_is_rejected():
    df = valid_customer()
    df.loc[0, "customer_id"] = None
    errors = validate_customer_data(df)
    assert any("customer_id contains missing" in e for e in errors)


def test_duplicate_hashed_identifier_is_rejected():
    df = pd.concat([valid_customer(), valid_customer()], ignore_index=True)
    df.loc[1, "customer_id"] = "CUST-002"
    errors = validate_customer_data(df)
    assert any("customer_email_hash contains duplicate" in e for e in errors)


def test_invalid_purchase_date_is_rejected():
    df = valid_customer()
    df.loc[0, "first_purchase_date"] = "not-a-date"
    errors = validate_customer_data(df)
    assert any("invalid or missing dates" in e for e in errors)


def test_negative_lifetime_orders_are_rejected():
    df = valid_customer()
    df.loc[0, "lifetime_orders"] = -1
    errors = validate_customer_data(df)
    assert any("lifetime_orders contains negative" in e for e in errors)


def test_negative_revenue_is_rejected():
    df = valid_customer()
    df.loc[0, "lifetime_revenue"] = -10
    errors = validate_customer_data(df)
    assert any("lifetime_revenue contains negative" in e for e in errors)


def test_missing_required_column_is_rejected():
    df = valid_customer().drop(columns=["country"])
    errors = validate_customer_data(df)
    assert any("Missing required columns" in e for e in errors)


def test_invalid_marketing_opt_in_is_rejected():
    df = valid_customer()
    df["marketing_opt_in"] = df["marketing_opt_in"].astype(object)
    df.loc[0, "marketing_opt_in"] = "unknown"
    errors = validate_customer_data(df)
    assert any("marketing_opt_in" in e for e in errors)
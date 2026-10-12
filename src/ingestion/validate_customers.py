
import pandas as pd


REQUIRED_COLUMNS = {
    "customer_id",
    "customer_email_hash",
    "customer_type",
    "country",
    "acquisition_source",
    "first_purchase_date",
    "lifetime_orders",
    "lifetime_revenue",
    "marketing_opt_in",
    "loyalty_tier",
}


def validate_customer_data(df: pd.DataFrame) -> list[str]:
    """Return validation errors without modifying the input dataframe."""
    errors = []

    missing_columns = REQUIRED_COLUMNS - set(df.columns)
    if missing_columns:
        return [f"Missing required columns: {', '.join(sorted(missing_columns))}"]

    for column in ("customer_id", "customer_email_hash"):
        if df[column].isna().any():
            errors.append(f"{column} contains missing values")
        elif df[column].astype(str).str.strip().eq("").any():
            errors.append(f"{column} contains blank values")
        elif df[column].duplicated().any():
            errors.append(f"{column} contains duplicate values")

    for column in ("customer_type", "country", "acquisition_source"):
        if df[column].isna().any():
            errors.append(f"{column} contains missing values")
        elif df[column].astype(str).str.strip().eq("").any():
            errors.append(f"{column} contains blank values")

    dates = pd.to_datetime(df["first_purchase_date"], errors="coerce")
    if dates.isna().any():
        errors.append("first_purchase_date contains invalid or missing dates")

    for column in ("lifetime_orders", "lifetime_revenue"):
        values = pd.to_numeric(df[column], errors="coerce")
        if values.isna().any():
            errors.append(f"{column} contains non-numeric or missing values")
        elif (values < 0).any():
            errors.append(f"{column} contains negative values")

    opt_in = df["marketing_opt_in"]
    valid_boolean_values = opt_in.map(
        lambda value: isinstance(value, bool)
        or (
            isinstance(value, (int, float))
            and value in (0, 1)
        )
    )
    if opt_in.isna().any() or not valid_boolean_values.all():
        errors.append("marketing_opt_in must contain only boolean values")

    # Missing loyalty_tier is allowed; it may be legitimately unassigned.
    return errors

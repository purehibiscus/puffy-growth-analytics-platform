
import pandas as pd


def validate_refund_status(orders: pd.DataFrame) -> pd.DataFrame:
    """Flag suspicious status/refund combinations without altering source data."""
    required = {"order_id", "order_status", "refund_amount", "net_revenue"}
    missing = required - set(orders.columns)

    if missing:
        raise ValueError(
            f"Missing order columns: {', '.join(sorted(missing))}"
        )

    result = orders[
        ["order_id", "order_status", "refund_amount", "net_revenue"]
    ].copy()

    status = result["order_status"].astype("string").str.strip().str.lower()
    refunds = pd.to_numeric(result["refund_amount"], errors="coerce")
    revenue = pd.to_numeric(result["net_revenue"], errors="coerce")

    result["refund_status_issue"] = (
        ((status == "cancelled") & (revenue > 0))
        | ((status == "refunded") & (revenue > 0))
        | ((status == "partially_refunded") & (refunds <= 0))
        | (
            status.isin(["cancelled", "refunded", "partially_refunded"])
            & (refunds == 0)
        )
    ).fillna(False)

    result["refund_status_issue_reason"] = ""

    result.loc[
        (status == "cancelled") & (revenue > 0),
        "refund_status_issue_reason",
    ] = "Cancelled order has positive net revenue"

    result.loc[
        (status == "refunded") & (revenue > 0),
        "refund_status_issue_reason",
    ] = "Refunded order has positive net revenue"

    result.loc[
        (status == "partially_refunded") & (refunds <= 0),
        "refund_status_issue_reason",
    ] = "Partially refunded order has no positive refund amount"

    result.loc[
        status.isin(["cancelled", "refunded", "partially_refunded"])
        & (refunds == 0)
        & (result["refund_status_issue_reason"] == ""),
        "refund_status_issue_reason",
    ] = "Cancelled/refund-status order has zero refund amount"

    return result

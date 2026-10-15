select *
from {{ ref('fct_ga4_sequential_funnel_sessions') }}
where
    (has_ordered_add_to_cart
        and product_view_timestamp >= ordered_cart_timestamp)
    or (has_ordered_checkout
        and ordered_cart_timestamp >= ordered_checkout_timestamp)
    or (has_ordered_payment_info
        and ordered_checkout_timestamp >= ordered_payment_timestamp)
    or (has_ordered_purchase
        and ordered_payment_timestamp >= ordered_purchase_timestamp)
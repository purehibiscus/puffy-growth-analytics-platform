select *
from {{ ref('fct_ga4_sequential_funnel_sessions') }}
where
    (has_ordered_checkout and not has_ordered_add_to_cart)
    or (has_ordered_payment_info and not has_ordered_checkout)
    or (has_ordered_purchase and not has_ordered_payment_info)
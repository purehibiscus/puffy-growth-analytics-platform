
with sessions as (

    select *
    from {{ ref('fct_ga4_sessions') }}

)

select
    session_date as event_date,

    count(*) as total_sessions,

    countif(product_view_events > 0) as product_view_sessions,
    countif(add_to_cart_events > 0) as add_to_cart_sessions,
    countif(checkout_events > 0) as checkout_sessions,
    countif(payment_info_events > 0) as payment_info_sessions,
    countif(purchase_events > 0) as purchase_sessions,

    sum(product_view_events) as product_view_events,
    sum(add_to_cart_events) as add_to_cart_events,
    sum(checkout_events) as checkout_events,
    sum(payment_info_events) as payment_info_events,
    sum(purchase_events) as purchase_events,

    safe_divide(
        countif(add_to_cart_events > 0),
        countif(product_view_events > 0)
    ) as product_view_to_cart_rate,

    safe_divide(
        countif(checkout_events > 0),
        countif(add_to_cart_events > 0)
    ) as cart_to_checkout_rate,

    safe_divide(
        countif(purchase_events > 0),
        countif(checkout_events > 0)
    ) as checkout_to_purchase_rate,

    safe_divide(
        countif(purchase_events > 0),
        count(*)
    ) as session_purchase_rate,

    avg(session_duration_seconds) as avg_session_duration_seconds,
    avg(total_event_engagement_seconds) as avg_event_engagement_seconds,
    avg(avg_page_load_ms) as avg_page_load_ms

from sessions
group by event_date

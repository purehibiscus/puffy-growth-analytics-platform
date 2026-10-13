
with sessions as (

    select *
    from {{ ref('fct_ga4_sessions') }}

)

select
    session_date as event_date,

    coalesce(traffic_source, '(not set)') as traffic_source,
    coalesce(traffic_medium, '(not set)') as traffic_medium,
    coalesce(campaign, '(not set)') as campaign,
    coalesce(device_category, '(not set)') as device_category,
    coalesce(country, '(not set)') as country,
    coalesce(landing_page, '(not set)') as landing_page,

    count(*) as sessions,
    count(distinct user_id) as users,

    countif(product_view_events > 0) as product_view_sessions,
    countif(add_to_cart_events > 0) as add_to_cart_sessions,
    countif(checkout_events > 0) as checkout_sessions,
    countif(payment_info_events > 0) as payment_info_sessions,
    countif(purchase_events > 0) as purchase_sessions,

    sum(event_count) as total_events,
    sum(purchase_events) as purchase_events,

    safe_divide(
        countif(purchase_events > 0),
        count(*)
    ) as session_purchase_rate,

    avg(session_duration_seconds) as avg_session_duration_seconds,
    avg(total_event_engagement_seconds) as avg_event_engagement_seconds,
    avg(avg_page_load_ms) as avg_page_load_ms

from sessions
group by
    event_date,
    traffic_source,
    traffic_medium,
    campaign,
    device_category,
    country,
    landing_page

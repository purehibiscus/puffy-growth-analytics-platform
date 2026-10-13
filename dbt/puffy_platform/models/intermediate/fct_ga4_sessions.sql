
with events as (

    select *
    from {{ ref('stg_ga4_events') }}

),

session_summary as (

    select
        session_id,
        max(user_id) as user_id,

        min(event_timestamp) as session_start_timestamp,
        max(event_timestamp) as session_end_timestamp,

        date(min(event_timestamp)) as session_date,

        array_agg(
    traffic_source ignore nulls
    order by event_timestamp, event_id
    limit 1
)[safe_offset(0)] as traffic_source,

array_agg(
    traffic_medium ignore nulls
    order by event_timestamp, event_id
    limit 1
)[safe_offset(0)] as traffic_medium,

array_agg(
    campaign ignore nulls
    order by event_timestamp, event_id
    limit 1
)[safe_offset(0)] as campaign,

array_agg(
    landing_page ignore nulls
    order by event_timestamp, event_id
    limit 1
)[safe_offset(0)] as landing_page,

array_agg(
    device_category ignore nulls
    order by event_timestamp, event_id
    limit 1
)[safe_offset(0)] as device_category,

array_agg(
    country ignore nulls
    order by event_timestamp, event_id
    limit 1
)[safe_offset(0)] as country,

array_agg(
    browser ignore nulls
    order by event_timestamp, event_id
    limit 1
)[safe_offset(0)] as browser,

array_agg(
    operating_system ignore nulls
    order by event_timestamp, event_id
    limit 1
)[safe_offset(0)] as operating_system,

        count(*) as event_count,

        countif(event_name = 'session_start') as session_start_events,
        countif(event_name = 'view_item') as product_view_events,
        countif(event_name = 'add_to_cart') as add_to_cart_events,
        countif(event_name = 'begin_checkout') as checkout_events,
        countif(event_name = 'add_payment_info') as payment_info_events,
        countif(event_name = 'purchase') as purchase_events,

        sum(coalesce(engagement_seconds, 0)) as total_event_engagement_seconds,
        max(coalesce(engagement_seconds, 0)) as max_event_engagement_seconds,
        avg(page_load_ms) as avg_page_load_ms,
        max(scroll_depth_pct) as max_scroll_depth_pct

    from events
    group by session_id

)

select
    *,
    timestamp_diff(
        session_end_timestamp,
        session_start_timestamp,
        second
    ) as session_duration_seconds,

    purchase_events > 0 as has_purchase_event

from session_summary

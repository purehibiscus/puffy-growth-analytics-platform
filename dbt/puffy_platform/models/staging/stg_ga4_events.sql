
with source as (

    select *
    from {{ source('puffy_raw', 'ga4_events') }}

),

renamed as (

    select
        cast(event_id as string) as event_id,
        cast(event_timestamp as timestamp) as event_timestamp,
        date(cast(event_timestamp as timestamp)) as event_date,

        cast(user_id as string) as user_id,
        cast(session_id as string) as session_id,

        lower(trim(event_name)) as event_name,
        nullif(trim(page_location), '') as page_location,
        nullif(trim(landing_page), '') as landing_page,

        lower(nullif(trim(device_category), '')) as device_category,
        upper(nullif(trim(country), '')) as country,

        lower(nullif(trim(traffic_source), '')) as traffic_source,
        lower(nullif(trim(traffic_medium), '')) as traffic_medium,
        nullif(trim(campaign), '') as campaign,

        cast(product_id as string) as product_id,

        nullif(trim(experiment_id), '') as experiment_id,
        lower(nullif(trim(experiment_variant), '')) as experiment_variant,

        nullif(trim(browser), '') as browser,
        nullif(trim(os), '') as operating_system,

        safe_cast(engagement_seconds as int64) as engagement_seconds,
        safe_cast(scroll_depth_pct as int64) as scroll_depth_pct,
        safe_cast(page_load_ms as int64) as page_load_ms

    from source

)

select *
from renamed

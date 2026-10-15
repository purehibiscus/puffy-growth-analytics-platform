with session_events as (

    select
        session_id,
        date(min(event_timestamp)) as session_date,

        countif(event_name = 'session_start') as session_start_events,
        countif(event_name = 'view_item') as product_view_events,
        countif(event_name = 'add_to_cart') as add_to_cart_events,
        countif(event_name = 'begin_checkout') as checkout_events,
        countif(event_name = 'add_payment_info') as payment_info_events,
        countif(event_name = 'purchase') as purchase_events,

        array_agg(
            struct(
                event_name,
                event_timestamp,
                event_id
            )
            order by event_timestamp, event_id
        ) as events

    from {{ ref('stg_ga4_events') }}
    group by session_id

),

product_view_stage as (

    select
        *,

        (
            select as struct
                e.event_timestamp,
                e.event_id
            from unnest(events) as e
            where e.event_name = 'view_item'
            order by e.event_timestamp, e.event_id
            limit 1
        ) as view_item_event

    from session_events

),

cart_stage as (

    select
        *,

        (
            select as struct
                e.event_timestamp,
                e.event_id
            from unnest(events) as e
            where e.event_name = 'add_to_cart'
              and view_item_event is not null
              and (
                    e.event_timestamp > view_item_event.event_timestamp
                    or (
                        e.event_timestamp = view_item_event.event_timestamp
                        and e.event_id > view_item_event.event_id
                    )
              )
            order by e.event_timestamp, e.event_id
            limit 1
        ) as add_to_cart_event

    from product_view_stage

),

checkout_stage as (

    select
        *,

        (
            select as struct
                e.event_timestamp,
                e.event_id
            from unnest(events) as e
            where e.event_name = 'begin_checkout'
              and add_to_cart_event is not null
              and (
                    e.event_timestamp > add_to_cart_event.event_timestamp
                    or (
                        e.event_timestamp = add_to_cart_event.event_timestamp
                        and e.event_id > add_to_cart_event.event_id
                    )
              )
            order by e.event_timestamp, e.event_id
            limit 1
        ) as begin_checkout_event

    from cart_stage

),

payment_stage as (

    select
        *,

        (
            select as struct
                e.event_timestamp,
                e.event_id
            from unnest(events) as e
            where e.event_name = 'add_payment_info'
              and begin_checkout_event is not null
              and (
                    e.event_timestamp > begin_checkout_event.event_timestamp
                    or (
                        e.event_timestamp = begin_checkout_event.event_timestamp
                        and e.event_id > begin_checkout_event.event_id
                    )
              )
            order by e.event_timestamp, e.event_id
            limit 1
        ) as add_payment_info_event

    from checkout_stage

),

purchase_stage as (

    select
        *,

        (
            select as struct
                e.event_timestamp,
                e.event_id
            from unnest(events) as e
            where e.event_name = 'purchase'
              and add_payment_info_event is not null
              and (
                    e.event_timestamp > add_payment_info_event.event_timestamp
                    or (
                        e.event_timestamp = add_payment_info_event.event_timestamp
                        and e.event_id > add_payment_info_event.event_id
                    )
              )
            order by e.event_timestamp, e.event_id
            limit 1
        ) as purchase_event

    from payment_stage

)

select
    session_id,
    session_date,

    session_start_events,
    product_view_events,
    add_to_cart_events,
    checkout_events,
    payment_info_events,
    purchase_events,

    view_item_event is not null as has_product_view,

    add_to_cart_event is not null as has_ordered_add_to_cart,

    begin_checkout_event is not null as has_ordered_checkout,

    add_payment_info_event is not null as has_ordered_payment_info,

    purchase_event is not null as has_ordered_purchase,

    add_to_cart_events > 0
        and add_to_cart_event is null
        as has_cart_without_ordered_product_view,

    checkout_events > 0
        and begin_checkout_event is null
        as has_checkout_without_ordered_cart,

    payment_info_events > 0
        and add_payment_info_event is null
        as has_payment_without_ordered_checkout,

    purchase_events > 0
        and purchase_event is null
        as has_purchase_without_ordered_payment,

    view_item_event.event_timestamp as product_view_timestamp,
    add_to_cart_event.event_timestamp as ordered_cart_timestamp,
    begin_checkout_event.event_timestamp as ordered_checkout_timestamp,
    add_payment_info_event.event_timestamp as ordered_payment_timestamp,
    purchase_event.event_timestamp as ordered_purchase_timestamp

from purchase_stage
with source as (

    select *
    from {{ source('puffy_raw', 'shopify_orders') }}

),

renamed as (

    select
        cast(order_id as string) as order_id,
        cast(customer_id as string) as customer_id,
        safe_cast(order_timestamp as timestamp) as order_timestamp,
        lower(trim(order_status)) as order_status,
        safe_cast(subtotal as numeric) as subtotal,
        safe_cast(discount as numeric) as discount,
        safe_cast(shipping as numeric) as shipping,
        safe_cast(tax as numeric) as tax,
        safe_cast(refund_amount as numeric) as refund_amount,
        safe_cast(net_revenue as numeric) as net_revenue,
        upper(trim(currency)) as currency,
        lower(trim(payment_method)) as payment_method,
        upper(trim(shipping_country)) as shipping_country,
        lower(trim(device_category)) as device_category,
        landing_page,
        lower(trim(traffic_source)) as traffic_source,
        lower(trim(traffic_medium)) as traffic_medium,
        campaign,
        coupon_code,
        lower(trim(shipping_method)) as shipping_method,
        lower(trim(fulfillment_status)) as fulfillment_status
    from source

)

select * from renamed
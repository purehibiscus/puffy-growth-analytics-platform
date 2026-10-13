with source as (

    select *
    from {{ source('puffy_raw', 'shopify_order_items') }}

),

renamed as (

    select
        cast(order_item_id as string) as order_item_id,
        cast(order_id as string) as order_id,
        cast(product_id as string) as product_id,
        safe_cast(quantity as int64) as quantity,
        safe_cast(unit_price as numeric) as unit_price,
        safe_cast(discount as numeric) as discount,
        safe_cast(line_revenue as numeric) as line_revenue,
        safe_cast(gross_margin as numeric) as gross_margin
    from source

)

select * from renamed
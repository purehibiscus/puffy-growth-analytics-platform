with source as (

    select *
    from {{ source('puffy_raw', 'products') }}

),

renamed as (

    select
        cast(product_id as string) as product_id,
        trim(product_name) as product_name,
        trim(category) as category,
        trim(product_type) as product_type,
        trim(vendor) as vendor,
        safe_cast(price as numeric) as price,
        safe_cast(cost as numeric) as cost,
        trim(sku) as sku,
        safe_cast(inventory_qty as int64) as inventory_qty,
        safe_cast(rating as numeric) as rating,
        safe_cast(review_count as int64) as review_count,
        safe_cast(created_at as timestamp) as created_at,
        lower(trim(status)) as status
    from source

)

select * from renamed
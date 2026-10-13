with source as (

    select *
    from {{ source('puffy_raw', 'customers') }}

),

renamed as (

    select
        cast(customer_id as string) as customer_id,
        cast(customer_email_hash as string) as customer_email_hash,
        lower(trim(customer_type)) as customer_type,
        upper(trim(country)) as country,
        lower(trim(acquisition_source)) as acquisition_source,
        safe_cast(first_purchase_date as date) as first_purchase_date,
        safe_cast(lifetime_orders as int64) as lifetime_orders,
        safe_cast(lifetime_revenue as numeric) as lifetime_revenue,
        safe_cast(marketing_opt_in as bool) as marketing_opt_in,
        nullif(lower(trim(loyalty_tier)), '') as loyalty_tier
    from source

)

select * from renamed
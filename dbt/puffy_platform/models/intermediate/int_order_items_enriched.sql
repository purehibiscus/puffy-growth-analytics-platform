
with order_items as (

    select *
    from {{ ref('stg_shopify_order_items') }}

),

products as (

    select *
    from {{ ref('stg_products') }}

)

select
    oi.order_item_id,
    oi.order_id,
    oi.product_id,
    p.product_name,
    p.category,
    p.product_type,
    p.vendor,
    oi.quantity,
    oi.unit_price,
    oi.discount,
    oi.line_revenue,
    oi.gross_margin,
    safe_divide(oi.gross_margin, oi.line_revenue) as gross_margin_rate
from order_items oi
left join products p
    on oi.product_id = p.product_id

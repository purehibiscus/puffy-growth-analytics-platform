
with orders as (

    select *
    from {{ ref('stg_shopify_orders') }}

),

order_item_metrics as (

    select
        order_id,
        count(*) as order_item_count,
        sum(quantity) as units_ordered,
        sum(line_revenue) as item_revenue,
        sum(gross_margin) as item_gross_margin
    from {{ ref('int_order_items_enriched') }}
    group by order_id

)

select
    o.order_id,
    o.customer_id,
    o.order_timestamp,
    date(o.order_timestamp) as order_date,
    o.order_status,
    o.fulfillment_status,
    o.currency,
    o.subtotal,
    o.discount,
    o.shipping,
    o.tax,
    o.refund_amount,
    o.net_revenue,
    o.payment_method,
    o.shipping_country,
    o.device_category,
    o.landing_page,
    o.traffic_source,
    o.traffic_medium,
    o.campaign,
    o.coupon_code,
    coalesce(i.order_item_count, 0) as order_item_count,
    coalesce(i.units_ordered, 0) as units_ordered,
    coalesce(i.item_revenue, 0) as item_revenue,
    coalesce(i.item_gross_margin, 0) as item_gross_margin
from orders o
left join order_item_metrics i
    on o.order_id = i.order_id

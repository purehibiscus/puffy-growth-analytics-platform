
with customers as (

    select *
    from {{ ref('stg_customers') }}

),

order_metrics as (

    select
        customer_id,
        count(*) as total_orders,
        countif(order_status not in ('cancelled', 'refunded'))
            as non_cancelled_non_refunded_orders,
        sum(net_revenue) as total_net_revenue,
        min(order_date) as first_order_date,
        max(order_date) as most_recent_order_date
    from {{ ref('fct_orders') }}
    group by customer_id

)

select
    c.customer_id,
    c.customer_email_hash,
    c.customer_type,
    c.country,
    c.acquisition_source,
    c.first_purchase_date,
    c.lifetime_orders,
    c.lifetime_revenue,
    c.marketing_opt_in,
    c.loyalty_tier,
    coalesce(o.total_orders, 0) as total_orders,
    coalesce(o.non_cancelled_non_refunded_orders, 0)
        as non_cancelled_non_refunded_orders,
    coalesce(o.total_net_revenue, 0) as total_net_revenue,
    o.first_order_date,
    o.most_recent_order_date
from customers c
left join order_metrics o
    on c.customer_id = o.customer_id

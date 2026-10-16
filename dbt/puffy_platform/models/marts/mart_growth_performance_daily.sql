with orders as (

    select *
    from {{ ref('fct_orders') }}

),

daily_growth as (

    select
        order_date,
        currency,
        traffic_source,
        traffic_medium,
        campaign,
        shipping_country,
        device_category,

        count(*) as total_orders,
        countif(
            order_status not in ('cancelled', 'refunded')
        ) as eligible_orders,

        countif(order_status = 'cancelled') as cancelled_orders,
        countif(order_status = 'refunded') as refunded_orders,
        countif(order_status = 'partially_refunded') as partially_refunded_orders,

        sum(units_ordered) as units_ordered,

        sum(net_revenue) as recorded_net_revenue,

        sum(
            case
                when order_status not in ('cancelled', 'refunded')
                    then net_revenue
                else 0
            end
        ) as eligible_net_revenue,

        sum(discount) as total_discounts,
        sum(refund_amount) as total_recorded_refunds,
        sum(shipping) as total_shipping,
        sum(tax) as total_tax,

        sum(item_revenue) as item_revenue,
        sum(item_gross_margin) as item_gross_margin

    from orders

    group by
        order_date,
        currency,
        traffic_source,
        traffic_medium,
        campaign,
        shipping_country,
        device_category

)

select
    *,
    safe_divide(
        eligible_net_revenue,
        eligible_orders
    ) as eligible_revenue_per_order,

    safe_divide(
        item_gross_margin,
        item_revenue
    ) as item_gross_margin_rate

from daily_growth
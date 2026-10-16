select *
from {{ ref('mart_growth_performance_daily') }}
where total_orders <= 0
   or eligible_orders < 0
   or eligible_orders > total_orders
   or eligible_net_revenue > recorded_net_revenue + 0.02
   or (
       eligible_orders = 0
       and eligible_revenue_per_order is not null
   )
   or (
       eligible_orders > 0
       and (
           eligible_revenue_per_order is null
           or abs(
               eligible_revenue_per_order
               - safe_divide(eligible_net_revenue, eligible_orders)
           ) > 0.02
       )
   )
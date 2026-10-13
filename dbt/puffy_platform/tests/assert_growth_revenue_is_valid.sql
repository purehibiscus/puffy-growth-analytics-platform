select *
from {{ ref('mart_growth_performance_daily') }}
where total_orders <= 0
   or eligible_net_revenue > recorded_net_revenue + 0.02
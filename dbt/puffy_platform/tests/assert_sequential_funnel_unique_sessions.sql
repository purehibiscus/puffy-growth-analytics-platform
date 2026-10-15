select
    session_id,
    count(*) as row_count
from {{ ref('fct_ga4_sequential_funnel_sessions') }}
group by session_id
having count(*) > 1
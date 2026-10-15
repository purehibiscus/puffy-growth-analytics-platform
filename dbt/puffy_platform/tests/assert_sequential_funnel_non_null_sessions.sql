select *
from {{ ref('fct_ga4_sequential_funnel_sessions') }}
where session_id is null
-- Skeleton model (M1.2): the end of the chain. Replaced in M1.4.
select
    'gold' as layer,
    layer_order + 1 as layer_order,
    built_on_target
from {{ ref('smoke_silver') }}

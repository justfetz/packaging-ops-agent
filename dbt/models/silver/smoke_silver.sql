-- Skeleton model (M1.2): a ref() across layers. Replaced in M1.3.
select
    'silver' as layer,
    layer_order + 1 as layer_order,
    built_on_target
from {{ ref('smoke_bronze') }}

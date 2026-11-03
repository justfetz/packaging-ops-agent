-- Skeleton model (M1.2): proves the bronze schema, the target, and the
-- tests work end to end. Replaced by one model per raw feed in M1.3.
select
    'bronze' as layer,
    1 as layer_order,
    '{{ target.name }}' as built_on_target

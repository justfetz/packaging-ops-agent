-- Singular test (M1.2): proves tests/ is wired up on both targets. A dbt
-- test fails when it returns rows, so this returns a row only when the
-- skeleton chain lost or gained rows on the way to gold.
with counted as (
    select count(*) as n from {{ ref('smoke_gold') }}
)
select n from counted where n != 1

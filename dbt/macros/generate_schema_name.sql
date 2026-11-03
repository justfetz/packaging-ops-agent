{#-
  Put a model in exactly the schema its folder names (bronze, silver, gold)
  instead of dbt's default `<target schema>_<custom schema>`. On BigQuery the
  three datasets already exist (Terraform, infra/terraform/modules/bigquery_datasets);
  on DuckDB they are created in the project file on first build. A model with
  no custom schema lands in the target's schema.
-#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}

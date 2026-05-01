{# Config helpers exposed at compile time. The CLI reads
   gudu_lineage_config() output via dbt's metadata projection. #}

{% macro gudu_lineage_config() %}
  {% set defaults = {
    "backend": "anonymous",
    "url": none,
    "redact_literals": false,
    "min_node_coverage": none,
    "min_column_coverage": none
  } %}
  {% set user = var("gudu_lineage", {}) %}
  {% do return(defaults | combine(user)) %}
{% endmacro %}

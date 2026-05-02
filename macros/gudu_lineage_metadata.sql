{# Exposes package version + user config to dbt's metadata so the runtime CLI
   can read it from manifest.json without needing direct package introspection.
   Pure declarative — no runtime side effects. #}

{% macro gudu_lineage_metadata() %}
  {% do return({
      "package": "gudusoftware/gsp_dbt_lineage",
      "version": "0.0.1",
      "schema_version": "0.2.x",
      "config": var("gudu_lineage", {})
  }) %}
{% endmacro %}

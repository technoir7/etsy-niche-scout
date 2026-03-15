"""Export ranked niche results and comparison artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
from jinja2 import Template

from niche_scout.schemas import EnrichedKeywordRecord, RankedPayload, RunComparison
from niche_scout.utils import ensure_dir, read_json, write_json


REPORT_TEMPLATE = Template(
    """
# Etsy Niche Scout Report

Generated: {{ generated_at }}
Run: {{ run_id or "n/a" }}

## Opportunity Report

| Rank | Keyword | Blended Score | Base Score | Cluster | Family | Price | Search Volume |
| --- | --- | ---: | ---: | --- | --- | --- | ---: |
{% for row in top_rows -%}
| {{ loop.index }} | {{ row.query }} | {{ "%.1f"|format(row.blended_score or row.total_score) }} | {{ "%.1f"|format(row.total_score) }} | {{ row.cluster_label }} | {{ row.family_type or "n/a" }} | {{ row.median_price or "n/a" }} | {{ row.search_volume or "n/a" }} |
{% endfor %}

## Top Families

| Family | Score | Width | Type | Expansion | Bundle | Strategy |
| --- | ---: | ---: | --- | ---: | ---: | --- |
{% for family in families -%}
| {{ family.cluster_name }} | {{ "%.1f"|format(family.family_score) }} | {{ family.family_width }} | {{ family.family_type }} | {{ "%.1f"|format(family.expansion_potential_score) }} | {{ "%.1f"|format(family.bundle_potential_score) }} | {{ family.launch_strategy }} |
{% endfor %}

## Avoid List

{% for row in avoid_rows -%}
- `{{ row.query }}`: score {{ "%.1f"|format(row.blended_score or row.total_score) }}, warnings {{ row.warnings or "n/a" }}
{% endfor %}

## Import Impact

{% for row in import_rows -%}
- `{{ row.query }}`: import impact {{ "%.1f"|format(row.import_impact_score or 0.0) }}, volume {{ row.search_volume or "n/a" }}, competition {{ row.competition or "n/a" }}
{% endfor %}

## Cluster Notes

{% for family in families -%}
### {{ family.cluster_name }}

- Type: {{ family.family_type }}
- Product stack: {{ ", ".join(family.recommended_product_stack) if family.recommended_product_stack else "n/a" }}
- Adjacent expansions: {{ ", ".join(family.adjacent_expansions) if family.adjacent_expansions else "n/a" }}
- Rationale: {{ "; ".join(family.rationale) }}

{% endfor -%}
""".strip()
)


COMPARISON_TEMPLATE = Template(
    """
# Etsy Niche Scout Comparison

Baseline: {{ comparison.baseline_run_id }}
Comparison: {{ comparison.comparison_run_id }}

## Summary

- Changed keywords: {{ comparison.changed_keywords | length }}
- New keywords: {{ comparison.new_keywords | length }}
- Removed keywords: {{ comparison.removed_keywords | length }}
- Cluster changes: {{ comparison.changed_clusters | length }}

## Largest Score Moves

{% for row in comparison.changed_keywords[:15] -%}
- `{{ row.query }}`: {{ row.baseline_score or "n/a" }} -> {{ row.comparison_score or "n/a" }} (delta {{ row.score_delta or "n/a" }})
{% endfor %}

## New Keywords

{% for query in comparison.new_keywords[:20] -%}
- `{{ query }}`
{% endfor %}

## Removed Keywords

{% for query in comparison.removed_keywords[:20] -%}
- `{{ query }}`
{% endfor %}
""".strip()
)


def ranked_to_dataframe(ranked_keywords: list[EnrichedKeywordRecord]) -> pd.DataFrame:
    return pd.DataFrame([item.to_flat_dict() for item in ranked_keywords])


def families_to_dataframe(payload: RankedPayload) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for family in payload.families:
        row = family.model_dump()
        for field in ("keywords", "rationale", "recommended_product_stack", "adjacent_expansions"):
            row[field] = ", ".join(row.get(field, []))
        rows.append(row)
    return pd.DataFrame(rows)


def listings_to_dataframe(payload: RankedPayload) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "query": result.query,
                "normalized_query": result.normalized_query,
                "search_url": result.search_url,
                "fetched_at": result.fetched_at,
                **listing.model_dump(),
            }
            for result in payload.search_results
            for listing in result.listings
        ]
    )


def export_csv(path: str | Path, ranked_keywords: list[EnrichedKeywordRecord]) -> Path:
    target = Path(path)
    ensure_dir(target.parent)
    ranked_to_dataframe(ranked_keywords).to_csv(target, index=False)
    return target


def export_json(path: str | Path, payload: Any) -> Path:
    if hasattr(payload, "model_dump"):
        return write_json(path, payload.model_dump(mode="json"))
    return write_json(path, payload)


def render_markdown_from_payload(payload: RankedPayload) -> str:
    dataframe = ranked_to_dataframe(payload.ranked_keywords)
    if dataframe.empty:
        return f"# Etsy Niche Scout Report\n\nGenerated: {payload.generated_at}\n\nNo ranked keywords were available.\n"
    family_rows = [family.model_dump() for family in payload.families[:10]]
    top_rows = dataframe.sort_values(["blended_score", "total_score"], ascending=False).head(15).fillna("").to_dict(orient="records")
    avoid_rows = dataframe.sort_values(["blended_score", "total_score"], ascending=True).head(8).fillna("").to_dict(orient="records")
    import_rows = (
        dataframe.sort_values("import_impact_score", ascending=False)
        .query("import_impact_score > 0")
        .head(10)
        .fillna("")
        .to_dict(orient="records")
    )
    return REPORT_TEMPLATE.render(
        generated_at=payload.generated_at,
        run_id=payload.run_id,
        top_rows=top_rows,
        families=family_rows,
        avoid_rows=avoid_rows,
        import_rows=import_rows,
    )


def export_markdown(path: str | Path, payload: RankedPayload) -> Path:
    target = Path(path)
    ensure_dir(target.parent)
    target.write_text(render_markdown_from_payload(payload) + "\n", encoding="utf-8")
    return target


def report_from_csv(csv_path: str | Path, markdown_path: str | Path) -> Path:
    dataframe = pd.read_csv(csv_path)
    if dataframe.empty:
        rendered = f"# Etsy Niche Scout Report\n\nGenerated: {Path(csv_path).stem}\n\nNo ranked keywords were available.\n"
    else:
        top_rows = dataframe.sort_values(
            by=[column for column in ("blended_score", "total_score") if column in dataframe.columns],
            ascending=False,
        ).head(15)
        lines = [
            "# Etsy Niche Scout Report",
            "",
            f"Generated: {Path(csv_path).stem}",
            "",
            "## Top Keywords",
            "",
        ]
        for _, row in top_rows.iterrows():
            score = row.get("blended_score", row.get("total_score", "n/a"))
            lines.append(f"- `{row.get('query', 'n/a')}`: score {score}, cluster {row.get('cluster_label', 'n/a')}")
        rendered = "\n".join(lines)
    target = Path(markdown_path)
    ensure_dir(target.parent)
    target.write_text(rendered + "\n", encoding="utf-8")
    return target


def report_from_json(json_path: str | Path, markdown_path: str | Path) -> Path:
    payload = RankedPayload.model_validate(read_json(json_path))
    return export_markdown(markdown_path, payload)


def export_comparison_csv(path: str | Path, comparison: RunComparison) -> Path:
    target = Path(path)
    ensure_dir(target.parent)
    rows = [
        {"event_type": "changed", **item.model_dump()}
        for item in comparison.changed_keywords
    ]
    rows.extend(
        {
            "event_type": "new",
            "query": query,
        }
        for query in comparison.new_keywords
    )
    rows.extend(
        {
            "event_type": "removed",
            "query": query,
        }
        for query in comparison.removed_keywords
    )
    pd.DataFrame(rows).to_csv(target, index=False)
    return target


def export_comparison_markdown(path: str | Path, comparison: RunComparison) -> Path:
    target = Path(path)
    ensure_dir(target.parent)
    target.write_text(COMPARISON_TEMPLATE.render(comparison=comparison) + "\n", encoding="utf-8")
    return target


def export_dataframe_csv(path: str | Path, dataframe: pd.DataFrame) -> Path:
    target = Path(path)
    ensure_dir(target.parent)
    dataframe.to_csv(target, index=False)
    return target

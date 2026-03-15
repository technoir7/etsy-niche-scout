"""External keyword metrics import and enrichment."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from statistics import mean

import pandas as pd
from rapidfuzz.fuzz import token_set_ratio

from niche_scout.clustering import canonicalize_keyword
from niche_scout.config import DefaultsConfig, ImportSourceConfig, ImportersConfig, ScoringConfig, ClusteringConfig
from niche_scout.schemas import EnrichedKeywordRecord, ExternalKeywordMetrics, MetricsMergeContext, RankedPayload
from niche_scout.utils import normalize_header, normalize_text, parse_float


IMPORT_FIELDS = ("keyword", "search_volume", "clicks", "ctr", "competition", "trend", "avg_price")


def resolve_source_config(source: str, config: ImportersConfig) -> ImportSourceConfig:
    return config.sources.get(source, config.sources.get("default", ImportSourceConfig()))


def resolve_column_mapping(
    columns: list[str],
    source_config: ImportSourceConfig,
    default_config: ImportSourceConfig | None = None,
) -> dict[str, str]:
    normalized_columns = {normalize_header(column): column for column in columns}
    resolved: dict[str, str] = {}
    for field in IMPORT_FIELDS:
        aliases = list(getattr(source_config, field, []))
        if default_config is not None:
            for alias in getattr(default_config, field, []):
                if alias not in aliases:
                    aliases.append(alias)
        for alias in aliases:
            normalized_alias = normalize_header(alias)
            if normalized_alias in normalized_columns:
                resolved[field] = normalized_columns[normalized_alias]
                break
    return resolved


def import_metrics_csv(path: str | Path, source: str, config: ImportersConfig) -> list[ExternalKeywordMetrics]:
    dataframe = pd.read_csv(path)
    source_config = resolve_source_config(source, config)
    column_mapping = resolve_column_mapping(
        list(dataframe.columns),
        source_config,
        config.sources.get("default"),
    )
    if "keyword" not in column_mapping:
        raise ValueError("Could not resolve a keyword column from the CSV.")

    imported: list[ExternalKeywordMetrics] = []
    for row in dataframe.to_dict(orient="records"):
        keyword = row.get(column_mapping["keyword"])
        if keyword is None or not str(keyword).strip():
            continue
        normalized_keyword = normalize_text(str(keyword))
        raw_metrics = {normalize_header(key): value for key, value in row.items()}
        imported.append(
            ExternalKeywordMetrics(
                keyword=str(keyword).strip(),
                normalized_keyword=normalized_keyword,
                source=source,
                search_volume=parse_float(row.get(column_mapping.get("search_volume", ""))),
                clicks=parse_float(row.get(column_mapping.get("clicks", ""))),
                ctr=parse_float(row.get(column_mapping.get("ctr", ""))),
                competition=parse_float(row.get(column_mapping.get("competition", ""))),
                trend=parse_float(row.get(column_mapping.get("trend", ""))),
                avg_price=parse_float(row.get(column_mapping.get("avg_price", ""))),
                raw_metrics=raw_metrics,
            )
        )
    return imported


def _aggregate_metrics(records: list[ExternalKeywordMetrics], scoring: ScoringConfig) -> MetricsMergeContext:
    if not records:
        return MetricsMergeContext()

    def avg_metric(name: str) -> float | None:
        values = [getattr(record, name) for record in records if getattr(record, name) is not None]
        return round(mean(values), 2) if values else None

    search_volume = avg_metric("search_volume")
    clicks = avg_metric("clicks")
    ctr = avg_metric("ctr")
    competition = avg_metric("competition")
    trend = avg_metric("trend")
    avg_price = avg_metric("avg_price")

    caps = scoring.external_score_caps
    # External score is intentionally capped per signal so imported CSVs can
    # influence ranking without overwhelming first-page Etsy evidence.
    # Each metric contributes up to its configured cap after lightweight
    # normalization by a divisor where appropriate.
    metrics_score = 0.0
    if search_volume is not None:
        metrics_score += min(caps.search_volume_cap, search_volume / caps.search_volume_divisor)
    if clicks is not None:
        metrics_score += min(caps.clicks_cap, clicks / caps.clicks_divisor)
    if ctr is not None:
        metrics_score += min(caps.ctr_cap, ctr)
    if competition is not None:
        metrics_score += max(0.0, caps.competition_cap - min(caps.competition_cap, competition / caps.competition_divisor))
    if trend is not None:
        metrics_score += min(caps.trend_cap, max(0.0, trend))
    if avg_price is not None:
        metrics_score += min(caps.avg_price_cap, max(0.0, avg_price / caps.avg_price_divisor))

    return MetricsMergeContext(
        source_count=len({record.source for record in records}),
        search_volume=search_volume,
        clicks=clicks,
        ctr=ctr,
        competition=competition,
        trend=trend,
        avg_price=avg_price,
        external_metrics_score=round(min(metrics_score, 100.0), 2),
    )


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left.intersection(right)) / len(left.union(right))


def _match_metrics_for_keyword(
    item: EnrichedKeywordRecord,
    direct_lookup: dict[str, list[ExternalKeywordMetrics]],
    canonical_lookup: dict[tuple[str | None, str | None, tuple[str, ...]], list[ExternalKeywordMetrics]],
    family_lookup: dict[tuple[str | None, str | None], list[ExternalKeywordMetrics]],
    metrics_canonical_lookup: dict[str, tuple[str | None, str | None, tuple[str, ...]]],
) -> tuple[list[ExternalKeywordMetrics], str | None, float]:
    direct_matches = direct_lookup.get(item.normalized_query, [])
    if direct_matches:
        return direct_matches, "exact", 1.0

    canonical_key = (item.canonical_profession, item.canonical_product_type, tuple(item.canonical_core))
    exact_canonical = canonical_lookup.get(canonical_key, [])
    if exact_canonical:
        return exact_canonical, "canonical_exact", 0.9

    if not item.canonical_profession and not item.canonical_product_type:
        return [], None, 0.0

    family_candidates = family_lookup.get((item.canonical_profession, item.canonical_product_type), [])
    if not family_candidates:
        return [], None, 0.0

    scored_candidates: list[tuple[float, ExternalKeywordMetrics]] = []
    item_core = set(item.canonical_core)
    for candidate in family_candidates:
        candidate_key = metrics_canonical_lookup[candidate.normalized_keyword]
        candidate_core = set(candidate_key[2])
        jaccard = _jaccard(item_core, candidate_core)
        fuzzy = token_set_ratio(item.query, candidate.keyword) / 100.0
        score = max(jaccard, fuzzy)
        if score >= 0.62 or (item_core and candidate_core and len(item_core.intersection(candidate_core)) >= 1):
            scored_candidates.append((score, candidate))

    if not scored_candidates:
        return [], None, 0.0

    scored_candidates.sort(key=lambda pair: pair[0], reverse=True)
    top_matches = [candidate for _score, candidate in scored_candidates[:3]]
    confidence = round(sum(score for score, _candidate in scored_candidates[:3]) / min(len(scored_candidates), 3), 2)
    return top_matches, "family_fuzzy", confidence


def attach_external_metrics(
    payload: RankedPayload,
    imported_metrics: list[ExternalKeywordMetrics],
    defaults: DefaultsConfig,
    clustering: ClusteringConfig,
    scoring: ScoringConfig,
) -> RankedPayload:
    direct_lookup: dict[str, list[ExternalKeywordMetrics]] = defaultdict(list)
    canonical_lookup: dict[tuple[str | None, str | None, tuple[str, ...]], list[ExternalKeywordMetrics]] = defaultdict(list)
    family_lookup: dict[tuple[str | None, str | None], list[ExternalKeywordMetrics]] = defaultdict(list)
    metrics_canonical_lookup: dict[str, tuple[str | None, str | None, tuple[str, ...]]] = {}
    for metric in imported_metrics:
        direct_lookup[metric.normalized_keyword].append(metric)
        canonical = canonicalize_keyword(metric.keyword, defaults, clustering)
        canonical_key = (canonical.profession, canonical.product_type, canonical.core_tokens)
        canonical_lookup[canonical_key].append(metric)
        family_lookup[(canonical.profession, canonical.product_type)].append(metric)
        metrics_canonical_lookup[metric.normalized_keyword] = canonical_key

    enriched_keywords: list[EnrichedKeywordRecord] = []
    for item in payload.ranked_keywords:
        merged_matches, match_strategy, match_confidence = _match_metrics_for_keyword(
            item,
            direct_lookup,
            canonical_lookup,
            family_lookup,
            metrics_canonical_lookup,
        )
        context = _aggregate_metrics(merged_matches, scoring)
        base_score = item.score.total_score
        if context.external_metrics_score > 0:
            # Imported keyword metrics act as a capped bonus layered onto Etsy
            # evidence rather than replacing part of the base score.
            blended_score = round(min(100.0, base_score + context.external_metrics_score * 0.15), 2)
            import_impact = round(blended_score - base_score, 2)
            material_change = abs(import_impact) >= scoring.thresholds.recommendation_min_score * 0.05
        else:
            blended_score = base_score
            import_impact = 0.0
            material_change = False

        score = item.score.model_copy(
            update={
                "external_metrics_score": context.external_metrics_score,
                "blended_score": blended_score,
            }
        )
        enriched_context = context.model_copy(
            update={
                "import_impact_score": import_impact,
                "material_change": material_change,
                "match_strategy": match_strategy,
                "match_confidence": match_confidence,
            }
        )
        enriched_keywords.append(
            item.model_copy(
                update={
                    "imported_metrics": merged_matches,
                    "metrics_context": enriched_context,
                    "score": score,
                }
            )
        )

    enriched_keywords.sort(key=lambda item: item.score.blended_score or item.score.total_score, reverse=True)
    return payload.model_copy(update={"ranked_keywords": enriched_keywords})


def enrich_dataframe(dataframe: pd.DataFrame, imported_metrics: list[ExternalKeywordMetrics]) -> pd.DataFrame:
    metrics_rows = pd.DataFrame(
        [
            {
                "normalized_query": metric.normalized_keyword,
                "metrics_source": metric.source,
                "search_volume": metric.search_volume,
                "clicks": metric.clicks,
                "ctr": metric.ctr,
                "competition": metric.competition,
                "trend": metric.trend,
                "avg_price_external": metric.avg_price,
            }
            for metric in imported_metrics
        ]
    )
    if metrics_rows.empty:
        return dataframe
    grouped = metrics_rows.groupby("normalized_query", as_index=False).agg(
        {
            "metrics_source": lambda values: ", ".join(sorted(set(values))),
            "search_volume": "mean",
            "clicks": "mean",
            "ctr": "mean",
            "competition": "mean",
            "trend": "mean",
            "avg_price_external": "mean",
        }
    )
    merged = dataframe.merge(grouped, on="normalized_query", how="left")
    return merged

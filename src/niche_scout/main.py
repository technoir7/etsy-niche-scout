"""Programmatic orchestration entrypoints for Etsy Niche Scout."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from niche_scout.clustering import cluster_keywords, cluster_label
from niche_scout.comparison import compare_dataframes
from niche_scout.config import (
    ROOT_DIR,
    ClusteringConfig,
    DefaultsConfig,
    ImportersConfig,
    ScoringConfig,
    SelectorsConfig,
    load_clustering,
    load_defaults,
    load_importers,
    load_scoring,
    load_selectors,
)
from niche_scout.exporters import (
    export_comparison_csv,
    export_comparison_markdown,
    export_csv,
    export_dataframe_csv,
    export_json,
    export_markdown,
    families_to_dataframe,
    listings_to_dataframe,
    ranked_to_dataframe,
    report_from_csv,
)
from niche_scout.family_analysis import analyze_families
from niche_scout.importers import attach_external_metrics, enrich_dataframe, import_metrics_csv
from niche_scout.keyword_expansion import expand_keywords_with_seeds
from niche_scout.normalizer import normalize_results
from niche_scout.recommender import attach_recommendations
from niche_scout.scoring import score_keywords
from niche_scout.schemas import EnrichedKeywordRecord, KeywordFamily, RankedPayload, ScanPayload
from niche_scout.serp_collector import SerpCollector
from niche_scout.utils import ensure_dir, read_json, slugify, utc_now, write_json


def timestamp_stem(now: datetime | None = None) -> str:
    stamp = now or utc_now()
    return stamp.strftime("%Y%m%d-%H%M%S")


def _processed_dir(defaults: DefaultsConfig) -> Path:
    return ensure_dir(ROOT_DIR / defaults.paths.processed_dir)


def _reports_dir(defaults: DefaultsConfig) -> Path:
    return ensure_dir(ROOT_DIR / defaults.paths.reports_dir)


def _raw_dir(defaults: DefaultsConfig) -> Path:
    return ensure_dir(ROOT_DIR / defaults.paths.raw_dir)


def _input_dir() -> Path:
    return ensure_dir(ROOT_DIR / "data/input")


def save_scan_payload(payload: ScanPayload, stem: str, defaults: DefaultsConfig) -> dict[str, Path]:
    raw_dir = _raw_dir(defaults)
    latest_path = raw_dir / "latest.json"
    timestamped_path = raw_dir / f"{stem}.json"
    write_json(latest_path, payload.model_dump(mode="json"))
    write_json(timestamped_path, payload.model_dump(mode="json"))
    return {"raw_latest": latest_path, "raw_timestamped": timestamped_path}


def _group_records_by_cluster(records: list[EnrichedKeywordRecord]) -> dict[str, list[EnrichedKeywordRecord]]:
    grouped: dict[str, list[EnrichedKeywordRecord]] = {}
    for record in records:
        grouped.setdefault(record.cluster_id, []).append(record)
    return grouped


def _attach_family_fields(
    records: list[EnrichedKeywordRecord],
    families: list[KeywordFamily],
) -> list[EnrichedKeywordRecord]:
    family_lookup = {family.cluster_id: family for family in families}
    return [
        record.model_copy(
            update={
                "family_score": family_lookup[record.cluster_id].family_score if record.cluster_id in family_lookup else None,
                "family_width": family_lookup[record.cluster_id].family_width if record.cluster_id in family_lookup else 0,
                "expansion_potential_score": (
                    family_lookup[record.cluster_id].expansion_potential_score if record.cluster_id in family_lookup else None
                ),
                "bundle_potential_score": (
                    family_lookup[record.cluster_id].bundle_potential_score if record.cluster_id in family_lookup else None
                ),
                "family_type": family_lookup[record.cluster_id].family_type if record.cluster_id in family_lookup else None,
            }
        )
        for record in records
    ]


def _finalize_payload(
    payload: RankedPayload,
    scoring: ScoringConfig,
    clustering: ClusteringConfig,
) -> RankedPayload:
    provisional_keywords = attach_recommendations(payload.ranked_keywords, [], scoring, clustering)
    provisional_families = analyze_families(_group_records_by_cluster(provisional_keywords))
    family_aware_keywords = _attach_family_fields(provisional_keywords, provisional_families)
    finalized_keywords = attach_recommendations(family_aware_keywords, provisional_families, scoring, clustering)
    finalized_families = analyze_families(_group_records_by_cluster(finalized_keywords))
    finalized_keywords = _attach_family_fields(finalized_keywords, finalized_families)
    finalized_keywords.sort(key=lambda item: item.score.blended_score or item.score.total_score, reverse=True)
    return payload.model_copy(update={"ranked_keywords": finalized_keywords, "families": finalized_families})


def rank_scan_payload(
    payload: ScanPayload,
    defaults: DefaultsConfig,
    scoring: ScoringConfig,
    clustering: ClusteringConfig,
) -> RankedPayload:
    features = normalize_results(payload.results, scoring)
    scored_pairs = score_keywords(features, scoring)
    grouped, canonical_lookup = cluster_keywords([feature for feature, _score in scored_pairs], defaults, clustering)

    cluster_lookup: dict[str, tuple[str, str]] = {}
    for _root, members in grouped.items():
        label = cluster_label(members, defaults, clustering)
        cluster_id = slugify(label)
        for member in members:
            cluster_lookup[member.normalized_query] = (cluster_id, label)

    ranked_keywords = [
        EnrichedKeywordRecord(
            query=feature.query,
            normalized_query=feature.normalized_query,
            cluster_id=cluster_lookup[feature.normalized_query][0],
            cluster_label=cluster_lookup[feature.normalized_query][1],
            features=feature,
            score=score,
            canonical_profession=canonical_lookup[feature.normalized_query].profession,
            canonical_product_type=canonical_lookup[feature.normalized_query].product_type,
            canonical_core=list(canonical_lookup[feature.normalized_query].core_tokens),
        )
        for feature, score in scored_pairs
    ]
    ranked_payload = RankedPayload(
        run_id=timestamp_stem(),
        generated_at=utc_now(),
        seeds=payload.seeds,
        ranked_keywords=ranked_keywords,
        search_results=payload.results,
    )
    return _finalize_payload(ranked_payload, scoring, clustering)


def export_ranked_payload(payload: RankedPayload, stem: str, defaults: DefaultsConfig) -> dict[str, Path]:
    processed_dir = _processed_dir(defaults)
    reports_dir = _reports_dir(defaults)
    csv_latest = processed_dir / "latest.csv"
    csv_timestamped = processed_dir / f"{stem}.csv"
    families_latest = processed_dir / "families-latest.csv"
    families_timestamped = processed_dir / f"families-{stem}.csv"
    listings_latest = processed_dir / "listings-latest.csv"
    listings_timestamped = processed_dir / f"listings-{stem}.csv"
    json_latest = processed_dir / "latest.json"
    json_timestamped = processed_dir / f"{stem}.json"
    md_latest = reports_dir / "latest.md"
    md_timestamped = reports_dir / f"{stem}.md"

    families_df = families_to_dataframe(payload)
    listings_df = listings_to_dataframe(payload)
    export_csv(csv_latest, payload.ranked_keywords)
    export_csv(csv_timestamped, payload.ranked_keywords)
    export_json(json_latest, payload)
    export_json(json_timestamped, payload)
    export_markdown(md_latest, payload)
    export_markdown(md_timestamped, payload)
    export_dataframe_csv(families_latest, families_df)
    export_dataframe_csv(families_timestamped, families_df)
    export_dataframe_csv(listings_latest, listings_df)
    export_dataframe_csv(listings_timestamped, listings_df)

    return {
        "csv_latest": csv_latest,
        "csv_timestamped": csv_timestamped,
        "families_csv_latest": families_latest,
        "families_csv_timestamped": families_timestamped,
        "listings_csv_latest": listings_latest,
        "listings_csv_timestamped": listings_timestamped,
        "json_latest": json_latest,
        "json_timestamped": json_timestamped,
        "markdown_latest": md_latest,
        "markdown_timestamped": md_timestamped,
    }


def run_scan(
    seeds: list[str],
    top_n: int | None = None,
    use_cache: bool | None = None,
    refresh_cache: bool = False,
) -> dict[str, Path]:
    defaults = load_defaults()
    scoring = load_scoring()
    clustering = load_clustering()
    selectors = load_selectors()
    query_map = expand_keywords_with_seeds(seeds, defaults.expansion)
    payload = SerpCollector(defaults, selectors).collect(
        query_map,
        top_n=top_n,
        use_cache=use_cache,
        refresh_cache=refresh_cache,
    )
    stem = timestamp_stem()
    outputs = save_scan_payload(payload, stem, defaults)
    outputs.update(export_ranked_payload(rank_scan_payload(payload, defaults, scoring, clustering), stem, defaults))
    return outputs


def score_file(raw_path: str | Path) -> dict[str, Path]:
    defaults = load_defaults()
    scoring = load_scoring()
    clustering = load_clustering()
    payload = ScanPayload.model_validate(read_json(raw_path))
    stem = timestamp_stem()
    return export_ranked_payload(rank_scan_payload(payload, defaults, scoring, clustering), stem, defaults)


def load_ranked_payload(path: str | Path) -> RankedPayload:
    return RankedPayload.model_validate(read_json(path))


def import_metrics_file(path: str | Path, source: str = "erank") -> dict[str, Path]:
    importers = load_importers()
    input_dir = _input_dir()
    stem = timestamp_stem()
    imported = import_metrics_csv(path, source=source, config=importers)
    csv_path = input_dir / f"imported-metrics-{stem}.csv"
    json_path = input_dir / f"imported-metrics-{stem}.json"
    dataframe = pd.DataFrame([metric.model_dump() for metric in imported])
    dataframe.to_csv(csv_path, index=False)
    write_json(json_path, [metric.model_dump(mode="json") for metric in imported])
    return {"metrics_csv": csv_path, "metrics_json": json_path}


def enrich_file(input_path: str | Path, metrics_path: str | Path, source: str = "erank") -> dict[str, Path]:
    defaults = load_defaults()
    scoring = load_scoring()
    clustering = load_clustering()
    importers = load_importers()
    stem = timestamp_stem()
    imported = import_metrics_csv(metrics_path, source=source, config=importers)
    path = Path(input_path)
    processed_dir = _processed_dir(defaults)
    reports_dir = _reports_dir(defaults)
    if path.suffix.lower() == ".json":
        payload = load_ranked_payload(path)
        enriched = attach_external_metrics(payload, imported, defaults, clustering, scoring)
        finalized = _finalize_payload(enriched, scoring, clustering)
        return export_ranked_payload(finalized, stem, defaults)

    dataframe = pd.read_csv(path)
    enriched_df = enrich_dataframe(dataframe, imported)
    csv_path = processed_dir / f"enriched-{stem}.csv"
    json_path = processed_dir / f"enriched-{stem}.json"
    report_path = reports_dir / f"enriched-{stem}.md"
    enriched_df.to_csv(csv_path, index=False)
    enriched_df.to_json(json_path, orient="records", indent=2)
    report_from_csv(csv_path, report_path)
    return {"csv": csv_path, "json": json_path, "markdown": report_path}


def compare_files(baseline_path: str | Path, comparison_path: str | Path) -> dict[str, Path]:
    defaults = load_defaults()
    clustering = load_clustering()
    baseline = _load_comparable_dataframe(baseline_path)
    comparison = _load_comparable_dataframe(comparison_path)
    stem = timestamp_stem()
    run_ids = (Path(baseline_path).stem, Path(comparison_path).stem)
    comparison_payload = compare_dataframes(baseline, comparison, run_ids, clustering)
    comparison_dir = _processed_dir(defaults)
    reports_dir = _reports_dir(defaults)
    csv_path = comparison_dir / f"comparison-{stem}.csv"
    json_path = comparison_dir / f"comparison-{stem}.json"
    md_path = reports_dir / f"comparison-{stem}.md"
    export_comparison_csv(csv_path, comparison_payload)
    export_json(json_path, comparison_payload)
    export_comparison_markdown(md_path, comparison_payload)
    return {"comparison_csv": csv_path, "comparison_json": json_path, "comparison_markdown": md_path}


def _load_comparable_dataframe(path: str | Path) -> pd.DataFrame:
    file_path = Path(path)
    if file_path.suffix.lower() == ".json":
        payload = load_ranked_payload(file_path)
        return ranked_to_dataframe(payload.ranked_keywords)
    return pd.read_csv(file_path)

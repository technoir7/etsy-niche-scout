"""Typed data models for the niche scouting pipeline."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ListingSignal(BaseModel):
    query: str
    title: str | None = None
    price: float | None = None
    currency: str | None = None
    review_count: int | None = None
    star_rating: float | None = None
    shop_name: str | None = None
    bestseller: bool = False
    digital_product: bool = False
    listing_url: str | None = None
    image_url: str | None = None
    rank_position: int


class SearchResultPage(BaseModel):
    query: str
    normalized_query: str
    seed_query: str | None = None
    search_url: str
    result_count_text: str | None = None
    parsed_result_count: int | None = None
    fetched_at: datetime
    listings: list[ListingSignal] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    raw_html_path: str | None = None
    screenshot_path: str | None = None


class KeywordFeatures(BaseModel):
    query: str
    normalized_query: str
    seed_query: str | None = None
    result_count_estimate: int | None = None
    result_count_text: str | None = None
    listing_count: int = 0
    median_price: float | None = None
    mean_price: float | None = None
    median_review_count: float | None = None
    max_review_count: int | None = None
    bestseller_count: int = 0
    digital_share: float = 0.0
    share_low_review: float = 0.0
    title_similarity_concentration: float = 0.0
    dominant_shop_share: float = 0.0
    keyword_title_shares: dict[str, float] = Field(default_factory=dict)
    distinct_shop_count: int = 0
    titles: list[str] = Field(default_factory=list)
    shops: list[str] = Field(default_factory=list)
    listing_urls: list[str] = Field(default_factory=list)


class ScoreBreakdown(BaseModel):
    buyer_intent_score: float
    accessibility_score: float
    monetization_score: float
    proof_of_sales_score: float
    differentiation_score: float
    saturation_penalty: float
    external_metrics_score: float = 0.0
    total_score: float
    blended_score: float | None = None


class ExternalKeywordMetrics(BaseModel):
    keyword: str
    normalized_keyword: str
    source: str
    search_volume: float | None = None
    clicks: float | None = None
    ctr: float | None = None
    competition: float | None = None
    trend: float | None = None
    avg_price: float | None = None
    raw_metrics: dict[str, Any] = Field(default_factory=dict)


class MetricsMergeContext(BaseModel):
    source_count: int = 0
    search_volume: float | None = None
    clicks: float | None = None
    ctr: float | None = None
    competition: float | None = None
    trend: float | None = None
    avg_price: float | None = None
    external_metrics_score: float = 0.0
    import_impact_score: float = 0.0
    material_change: bool = False
    match_strategy: str | None = None
    match_confidence: float = 0.0


class Recommendation(BaseModel):
    first_product: str
    bundle_idea: str
    target_price_range: str
    differentiation_angle: str
    launch_format: str
    likely_buyer_persona: str = ""
    product_angle: str = ""
    differentiation_suggestions: list[str] = Field(default_factory=list)
    thumbnail_title_hints: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    niche_label: str = ""


class RankedKeyword(BaseModel):
    query: str
    normalized_query: str
    cluster_id: str
    cluster_label: str
    features: KeywordFeatures
    score: ScoreBreakdown
    recommendation: Recommendation | None = None
    canonical_profession: str | None = None
    canonical_product_type: str | None = None
    canonical_core: list[str] = Field(default_factory=list)
    family_score: float | None = None
    family_width: int = 0
    expansion_potential_score: float | None = None
    bundle_potential_score: float | None = None
    family_type: str | None = None

    def to_flat_dict(self) -> dict[str, Any]:
        feature_data = self.features.model_dump()
        score_data = self.score.model_dump()
        rec_data = self.recommendation.model_dump() if self.recommendation else {}
        for field in ("differentiation_suggestions", "thumbnail_title_hints", "warnings"):
            if field in rec_data:
                rec_data[field] = ", ".join(rec_data.get(field, []))
        keyword_title_shares = feature_data.pop("keyword_title_shares", {})
        flat: dict[str, Any] = {
            "query": self.query,
            "normalized_query": self.normalized_query,
            "cluster_id": self.cluster_id,
            "cluster_label": self.cluster_label,
            "canonical_profession": self.canonical_profession,
            "canonical_product_type": self.canonical_product_type,
            "canonical_core": ", ".join(self.canonical_core),
            "family_score": self.family_score,
            "family_width": self.family_width,
            "expansion_potential_score": self.expansion_potential_score,
            "bundle_potential_score": self.bundle_potential_score,
            "family_type": self.family_type,
            **feature_data,
            **score_data,
            **rec_data,
        }
        for key, value in keyword_title_shares.items():
            flat[f"title_share_{key}"] = value
        return flat


class EnrichedKeywordRecord(RankedKeyword):
    imported_metrics: list[ExternalKeywordMetrics] = Field(default_factory=list)
    metrics_context: MetricsMergeContext = Field(default_factory=MetricsMergeContext)

    def to_flat_dict(self) -> dict[str, Any]:
        flat = super().to_flat_dict()
        flat.update(self.metrics_context.model_dump())
        flat["metrics_sources"] = ", ".join(sorted({metric.source for metric in self.imported_metrics}))
        return flat


class KeywordFamily(BaseModel):
    cluster_id: str
    cluster_name: str
    keywords: list[str]
    avg_score: float
    max_score: float
    family_score: float
    family_width: int
    expansion_potential_score: float
    bundle_potential_score: float
    avg_monetization_score: float
    avg_accessibility_score: float
    avg_external_metrics_score: float = 0.0
    launch_strategy: str
    family_type: str
    recommended_product_stack: list[str] = Field(default_factory=list)
    adjacent_expansions: list[str] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)


class KeywordChange(BaseModel):
    query: str
    baseline_score: float | None = None
    comparison_score: float | None = None
    score_delta: float | None = None
    baseline_cluster_id: str | None = None
    comparison_cluster_id: str | None = None
    cluster_changed: bool = False
    search_volume_delta: float | None = None
    competition_delta: float | None = None


class RunComparison(BaseModel):
    baseline_run_id: str
    comparison_run_id: str
    changed_keywords: list[KeywordChange] = Field(default_factory=list)
    new_keywords: list[str] = Field(default_factory=list)
    removed_keywords: list[str] = Field(default_factory=list)
    changed_clusters: list[KeywordChange] = Field(default_factory=list)


class ScanPayload(BaseModel):
    generated_at: datetime
    seeds: list[str]
    expanded_queries: list[str]
    results: list[SearchResultPage]


class RankedPayload(BaseModel):
    run_id: str | None = None
    generated_at: datetime
    seeds: list[str]
    ranked_keywords: list[EnrichedKeywordRecord]
    families: list[KeywordFamily] = Field(default_factory=list)
    search_results: list[SearchResultPage] = Field(default_factory=list)

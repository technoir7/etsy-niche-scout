"""Configuration loading for YAML-backed settings."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


ROOT_DIR = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT_DIR / "config"


class PathsConfig(BaseModel):
    raw_dir: str
    processed_dir: str
    reports_dir: str
    screenshot_dir: str
    html_cache_dir: str


class RuntimeConfig(BaseModel):
    headless: bool = True
    locale: str = "en-US"
    timezone: str = "America/Los_Angeles"
    timeout_ms: int = 25_000
    delay_ms: int = 1_200
    retries: int = 3
    top_n: int = 24
    output_stem: str = "latest"
    browser_channel: str | None = None
    use_html_cache: bool = False


class EtsyConfig(BaseModel):
    base_url: str


class ExpansionConfig(BaseModel):
    max_candidates_per_seed: int = 20
    stopwords: list[str] = Field(default_factory=list)
    strip_tokens: list[str] = Field(default_factory=list)
    intent_tokens: list[str] = Field(default_factory=list)
    modifiers: list[str] = Field(default_factory=list)
    phrase_templates: list[str] = Field(default_factory=list)
    synonym_map: dict[str, list[str]] = Field(default_factory=dict)


class DefaultsConfig(BaseModel):
    paths: PathsConfig
    runtime: RuntimeConfig
    etsy: EtsyConfig
    expansion: ExpansionConfig


class ScoreWeights(BaseModel):
    buyer_intent_score: float
    accessibility_score: float
    monetization_score: float
    proof_of_sales_score: float
    differentiation_score: float
    saturation_penalty: float


class ScoreSignalWeights(BaseModel):
    buyer_intent_hit: float = 24.0
    positive_modifier_hit: float = 10.0
    positive_title_share: float = 20.0
    negative_modifier_hit: float = 18.0


class ExternalScoreCaps(BaseModel):
    search_volume_cap: float = 35.0
    search_volume_divisor: float = 100.0
    clicks_cap: float = 20.0
    clicks_divisor: float = 60.0
    ctr_cap: float = 20.0
    competition_cap: float = 15.0
    competition_divisor: float = 10.0
    trend_cap: float = 10.0
    avg_price_cap: float = 10.0
    avg_price_divisor: float = 3.0


class ScoringTokens(BaseModel):
    buyer_intent: list[str] = Field(default_factory=list)
    positive_modifiers: list[str] = Field(default_factory=list)
    negative_modifiers: list[str] = Field(default_factory=list)


class ScoringThresholds(BaseModel):
    low_review_max: int = 30
    strong_review_count: int = 150
    high_result_count: int = 20_000
    low_result_count: int = 1_500
    low_price: float = 5.0
    premium_price: float = 18.0
    dominant_shop_share: float = 0.35
    strong_similarity: float = 82.0
    recommendation_min_score: float = 55.0


class ScoringConfig(BaseModel):
    weights: ScoreWeights
    signal_weights: ScoreSignalWeights = Field(default_factory=ScoreSignalWeights)
    external_score_caps: ExternalScoreCaps = Field(default_factory=ExternalScoreCaps)
    tokens: ScoringTokens
    thresholds: ScoringThresholds


class SelectorGroup(BaseModel):
    result_count: list[str] = Field(default_factory=list)
    listing_cards: list[str] = Field(default_factory=list)
    title: list[str] = Field(default_factory=list)
    url: list[str] = Field(default_factory=list)
    shop_name: list[str] = Field(default_factory=list)
    price: list[str] = Field(default_factory=list)
    rating: list[str] = Field(default_factory=list)
    reviews: list[str] = Field(default_factory=list)
    bestseller: list[str] = Field(default_factory=list)
    digital: list[str] = Field(default_factory=list)
    image: list[str] = Field(default_factory=list)


class SelectorsConfig(BaseModel):
    search: SelectorGroup
    listing: SelectorGroup


class ImportSourceConfig(BaseModel):
    keyword: list[str] = Field(default_factory=list)
    search_volume: list[str] = Field(default_factory=list)
    clicks: list[str] = Field(default_factory=list)
    ctr: list[str] = Field(default_factory=list)
    competition: list[str] = Field(default_factory=list)
    trend: list[str] = Field(default_factory=list)
    avg_price: list[str] = Field(default_factory=list)


class ImportersConfig(BaseModel):
    sources: dict[str, ImportSourceConfig] = Field(default_factory=dict)


class ClusteringThresholds(BaseModel):
    duplicate_similarity: float = 90.0
    family_similarity: float = 78.0
    min_core_overlap: int = 1
    significant_score_delta: float = 8.0
    significant_metric_delta: float = 10.0
    scale_warning_threshold: int = 150


class ClusteringLexiconConfig(BaseModel):
    stopwords: list[str] = Field(default_factory=list)
    profession_aliases: dict[str, str] = Field(default_factory=dict)
    product_aliases: dict[str, str] = Field(default_factory=dict)
    filler_tokens: list[str] = Field(default_factory=list)
    personas: dict[str, str] = Field(default_factory=dict)


class ClusteringConfig(BaseModel):
    thresholds: ClusteringThresholds = Field(default_factory=ClusteringThresholds)
    lexicon: ClusteringLexiconConfig = Field(default_factory=ClusteringLexiconConfig)


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


@lru_cache(maxsize=1)
def load_defaults() -> DefaultsConfig:
    return DefaultsConfig.model_validate(_load_yaml(CONFIG_DIR / "defaults.yaml"))


@lru_cache(maxsize=1)
def load_scoring() -> ScoringConfig:
    return ScoringConfig.model_validate(_load_yaml(CONFIG_DIR / "scoring.yaml"))


@lru_cache(maxsize=1)
def load_selectors() -> SelectorsConfig:
    return SelectorsConfig.model_validate(_load_yaml(CONFIG_DIR / "selectors.yaml"))


@lru_cache(maxsize=1)
def load_importers() -> ImportersConfig:
    return ImportersConfig.model_validate(_load_yaml(CONFIG_DIR / "importers.yaml"))


@lru_cache(maxsize=1)
def load_clustering() -> ClusteringConfig:
    return ClusteringConfig.model_validate(_load_yaml(CONFIG_DIR / "clustering.yaml"))

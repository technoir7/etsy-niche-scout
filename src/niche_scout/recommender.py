"""Deterministic keyword and family recommendations."""

from __future__ import annotations

from collections import defaultdict

from niche_scout.config import ClusteringConfig, ScoringConfig
from niche_scout.schemas import EnrichedKeywordRecord, KeywordFamily, Recommendation
from niche_scout.utils import round_price_range


PRODUCT_ANGLE_MAP = {
    "intake form": "Position as a client-ready intake workflow that saves admin time.",
    "notes": "Lead with compliance-friendly documentation speed.",
    "checklist": "Frame it as an operational checklist that reduces mistakes.",
    "onboarding": "Package it as a smoother onboarding handoff with fewer missed steps.",
    "template": "Sell fast customization and immediate deployment.",
    "bundle": "Position it as a complete toolkit instead of a one-off file.",
    "planner": "Lead with planning clarity and repeat-use value.",
    "pricing": "Frame it as a pricing confidence asset that prevents undercharging.",
    "contract": "Lead with professional polish and faster client close.",
    "invoice": "Sell speed of billing and cleaner client operations.",
    "welcome book": "Position it as a polished client or guest experience asset.",
}


def _buyer_persona(item: EnrichedKeywordRecord, clustering: ClusteringConfig) -> str:
    if item.canonical_profession and item.canonical_profession in clustering.lexicon.personas:
        return clustering.lexicon.personas[item.canonical_profession]
    return "professional buyer looking for a ready-to-use workflow asset"


def _product_angle(item: EnrichedKeywordRecord) -> str:
    if item.canonical_product_type and item.canonical_product_type in PRODUCT_ANGLE_MAP:
        return PRODUCT_ANGLE_MAP[item.canonical_product_type]
    return "Sell speed, clarity, and immediate usability over aesthetics."


def _warnings(item: EnrichedKeywordRecord, scoring: ScoringConfig) -> list[str]:
    warnings: list[str] = []
    if item.features.listing_count == 0:
        warnings.append("No listing data was collected for this keyword. Treat the score as degraded.")
    if item.features.title_similarity_concentration >= scoring.thresholds.strong_similarity:
        warnings.append("First-page titles are highly repetitive.")
    if item.features.dominant_shop_share >= scoring.thresholds.dominant_shop_share:
        warnings.append("A few shops dominate the first page.")
    if item.features.listing_count > 0 and (item.features.median_price or 0.0) <= scoring.thresholds.low_price:
        warnings.append("Price floor is weak on the first page.")
    if item.metrics_context.competition and item.metrics_context.competition >= 80:
        warnings.append("Imported competition metric is elevated.")
    return warnings


def build_recommendation(
    item: EnrichedKeywordRecord,
    cluster_members: list[EnrichedKeywordRecord],
    family: KeywordFamily | None,
    scoring: ScoringConfig,
    clustering: ClusteringConfig,
) -> Recommendation | None:
    effective_score = item.score.blended_score or item.score.total_score
    warnings = _warnings(item, scoring)
    warning_only = item.features.listing_count == 0
    if effective_score < scoring.thresholds.recommendation_min_score and not warning_only:
        return None

    bundle_bias = len(cluster_members) >= 3 or bool(family and family.bundle_potential_score >= 60)
    base_product = item.query if any(token in item.query for token in scoring.tokens.buyer_intent) else f"{item.query} template"
    bundle_idea = " + ".join(member.query for member in cluster_members[:3])
    differentiation_suggestions = [
        "Use a profession-specific headline instead of a generic template title.",
        "Show the editable workflow state in the thumbnail, not just the static page.",
    ]
    if warning_only:
        differentiation_angle = "Verify the live SERP manually before acting on this keyword."
    elif item.features.keyword_title_shares.get("editable", 0.0) < 0.35:
        differentiation_angle = "Win on editability and operational specificity."
        differentiation_suggestions.append("Offer Canva + PDF versions from day one.")
    elif item.features.title_similarity_concentration > scoring.thresholds.strong_similarity:
        differentiation_angle = "Narrow to a sub-workflow or buyer stage to escape saturation."
        differentiation_suggestions.append("Target a narrower workflow stage or persona.")
    else:
        differentiation_angle = "Build a compact operational toolkit around the core SKU."
        differentiation_suggestions.append("Cross-sell the next adjacent workflow asset in the listing image set.")

    thumbnail_hints = [
        f"Lead image should name the buyer and the asset: {item.canonical_profession or 'professional'} + {item.canonical_product_type or 'template'}.",
        "Show 2-3 filled example pages to signal practical utility fast.",
    ]
    if family:
        niche_label = "standalone" if family.family_width <= 1 else family.family_type
    else:
        niche_label = "standalone"

    return Recommendation(
        first_product=base_product,
        bundle_idea=bundle_idea,
        target_price_range=round_price_range(item.metrics_context.avg_price or item.features.median_price),
        differentiation_angle=differentiation_angle,
        launch_format="small family" if bundle_bias else "single product",
        likely_buyer_persona=_buyer_persona(item, clustering),
        product_angle=_product_angle(item),
        differentiation_suggestions=differentiation_suggestions,
        thumbnail_title_hints=thumbnail_hints,
        warnings=warnings,
        niche_label=niche_label,
    )


def attach_recommendations(
    ranked_keywords: list[EnrichedKeywordRecord],
    families: list[KeywordFamily],
    scoring: ScoringConfig,
    clustering: ClusteringConfig,
) -> list[EnrichedKeywordRecord]:
    grouped: dict[str, list[EnrichedKeywordRecord]] = defaultdict(list)
    for item in ranked_keywords:
        grouped[item.cluster_id].append(item)
    family_lookup = {family.cluster_id: family for family in families}

    enriched: list[EnrichedKeywordRecord] = []
    for item in ranked_keywords:
        recommendation = build_recommendation(
            item,
            grouped[item.cluster_id],
            family_lookup.get(item.cluster_id),
            scoring,
            clustering,
        )
        enriched.append(item.model_copy(update={"recommendation": recommendation}))
    return enriched

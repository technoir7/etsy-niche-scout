"""Transparent heuristic scoring for Etsy niche opportunities."""

from __future__ import annotations

from niche_scout.config import ScoringConfig
from niche_scout.schemas import KeywordFeatures, ScoreBreakdown


def clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, value))


def linear_score(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    return clamp((value - low) / (high - low) * 100.0)


def inverse_linear_score(value: float, low: float, high: float) -> float:
    return 100.0 - linear_score(value, low, high)


def phrase_hits(text: str, phrases: list[str]) -> int:
    lowered = text.lower()
    return sum(1 for phrase in phrases if phrase in lowered)


def score_keyword(features: KeywordFeatures, scoring: ScoringConfig) -> ScoreBreakdown:
    thresholds = scoring.thresholds
    signal_weights = scoring.signal_weights
    buyer_intent_hits = phrase_hits(features.query, scoring.tokens.buyer_intent)
    positive_modifier_hits = phrase_hits(features.query, scoring.tokens.positive_modifiers)
    negative_modifier_hits = phrase_hits(features.query, scoring.tokens.negative_modifiers)
    avg_positive_title_share = (
        sum(features.keyword_title_shares.get(token, 0.0) for token in scoring.tokens.positive_modifiers)
        / max(len(scoring.tokens.positive_modifiers), 1)
    )

    buyer_intent_score = clamp(
        buyer_intent_hits * signal_weights.buyer_intent_hit
        + positive_modifier_hits * signal_weights.positive_modifier_hit
        + avg_positive_title_share * signal_weights.positive_title_share
        - negative_modifier_hits * signal_weights.negative_modifier_hit
    )

    result_count = float(features.result_count_estimate or thresholds.high_result_count)
    accessibility_score = clamp(
        inverse_linear_score(result_count, thresholds.low_result_count, thresholds.high_result_count) * 0.45
        + features.share_low_review * 100 * 0.35
        + (1.0 - features.dominant_shop_share) * 100 * 0.20
    )

    median_price = float(features.median_price or thresholds.low_price)
    mean_price = float(features.mean_price or thresholds.low_price)
    monetization_score = clamp(
        linear_score(median_price, thresholds.low_price, thresholds.premium_price) * 0.55
        + linear_score(mean_price, thresholds.low_price, thresholds.premium_price) * 0.35
        + features.digital_share * 100 * 0.10
    )

    median_review_count = float(features.median_review_count or 0.0)
    bestseller_share = features.bestseller_count / max(features.listing_count, 1)
    proof_of_sales_score = clamp(
        linear_score(median_review_count, 0, thresholds.strong_review_count) * 0.65
        + bestseller_share * 100 * 0.35
    )

    editable_gap = 1.0 - features.keyword_title_shares.get("editable", 0.0)
    canva_gap = 1.0 - features.keyword_title_shares.get("canva", 0.0)
    differentiation_score = clamp(
        inverse_linear_score(features.title_similarity_concentration, 35, thresholds.strong_similarity) * 0.60
        + editable_gap * 100 * 0.20
        + canva_gap * 100 * 0.10
        + (1.0 - features.dominant_shop_share) * 100 * 0.10
    )

    saturation_penalty = clamp(
        linear_score(result_count, thresholds.low_result_count, thresholds.high_result_count) * 0.45
        + linear_score(features.title_similarity_concentration, 35, thresholds.strong_similarity) * 0.35
        + linear_score(features.dominant_shop_share, 0.10, thresholds.dominant_shop_share) * 0.15
        + inverse_linear_score(median_price, thresholds.low_price, thresholds.premium_price) * 0.05
    )

    total_score = clamp(
        buyer_intent_score * scoring.weights.buyer_intent_score
        + accessibility_score * scoring.weights.accessibility_score
        + monetization_score * scoring.weights.monetization_score
        + proof_of_sales_score * scoring.weights.proof_of_sales_score
        + differentiation_score * scoring.weights.differentiation_score
        - saturation_penalty * scoring.weights.saturation_penalty
    )

    return ScoreBreakdown(
        buyer_intent_score=round(buyer_intent_score, 2),
        accessibility_score=round(accessibility_score, 2),
        monetization_score=round(monetization_score, 2),
        proof_of_sales_score=round(proof_of_sales_score, 2),
        differentiation_score=round(differentiation_score, 2),
        saturation_penalty=round(saturation_penalty, 2),
        external_metrics_score=0.0,
        total_score=round(total_score, 2),
        blended_score=round(total_score, 2),
    )


def score_keywords(features: list[KeywordFeatures], scoring: ScoringConfig) -> list[tuple[KeywordFeatures, ScoreBreakdown]]:
    scored = [(feature, score_keyword(feature, scoring)) for feature in features]
    return sorted(scored, key=lambda item: item[1].total_score, reverse=True)

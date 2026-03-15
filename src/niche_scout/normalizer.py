"""Build aggregate keyword-level features from raw listing data."""

from __future__ import annotations

from collections import Counter
from itertools import combinations
import logging
from statistics import mean, median

from rapidfuzz.fuzz import token_set_ratio

from niche_scout.config import ScoringConfig
from niche_scout.schemas import KeywordFeatures, SearchResultPage
from niche_scout.utils import tokenize

logger = logging.getLogger(__name__)


def safe_mean(values: list[float]) -> float | None:
    return mean(values) if values else None


def safe_median(values: list[float]) -> float | None:
    return median(values) if values else None


def title_similarity_score(titles: list[str]) -> float:
    if len(titles) < 2:
        return 0.0
    similarities = [token_set_ratio(left, right) for left, right in combinations(titles, 2)]
    return round(mean(similarities), 2) if similarities else 0.0


def keyword_title_shares(titles: list[str], tokens: list[str]) -> dict[str, float]:
    denominator = max(len(titles), 1)
    return {
        token: round(sum(1 for title in titles if token in title.lower()) / denominator, 3)
        for token in tokens
    }


def normalize_search_result(result: SearchResultPage, scoring: ScoringConfig) -> KeywordFeatures:
    if not result.listings:
        logger.warning("No listings extracted for keyword '%s' (%s)", result.query, result.normalized_query)
    prices = [listing.price for listing in result.listings if listing.price is not None]
    reviews = [float(listing.review_count) for listing in result.listings if listing.review_count is not None]
    titles = [listing.title for listing in result.listings if listing.title]
    shops = [listing.shop_name for listing in result.listings if listing.shop_name]
    shop_counts = Counter(shops)
    dominant_shop_share = max(shop_counts.values(), default=0) / max(len(shops), 1)
    low_review_max = scoring.thresholds.low_review_max

    return KeywordFeatures(
        query=result.query,
        normalized_query=result.normalized_query,
        seed_query=result.seed_query,
        result_count_estimate=result.parsed_result_count,
        result_count_text=result.result_count_text,
        listing_count=len(result.listings),
        median_price=safe_median([float(value) for value in prices]),
        mean_price=safe_mean([float(value) for value in prices]),
        median_review_count=safe_median(reviews),
        max_review_count=max((int(review) for review in reviews), default=None),
        bestseller_count=sum(1 for listing in result.listings if listing.bestseller),
        digital_share=round(
            sum(1 for listing in result.listings if listing.digital_product) / max(len(result.listings), 1),
            3,
        ),
        share_low_review=round(
            sum(1 for listing in result.listings if (listing.review_count or 0) <= low_review_max)
            / max(len(result.listings), 1),
            3,
        ),
        title_similarity_concentration=title_similarity_score(titles),
        dominant_shop_share=round(dominant_shop_share, 3),
        keyword_title_shares=keyword_title_shares(
            titles,
            scoring.tokens.positive_modifiers + scoring.tokens.buyer_intent,
        ),
        distinct_shop_count=len(shop_counts),
        titles=titles,
        shops=[shop for shop in shops if shop],
        listing_urls=[listing.listing_url for listing in result.listings if listing.listing_url],
    )


def normalize_results(results: list[SearchResultPage], scoring: ScoringConfig) -> list[KeywordFeatures]:
    normalized = [normalize_search_result(result, scoring) for result in results]
    return sorted(
        normalized,
        key=lambda item: (
            -(item.result_count_estimate or 0),
            -item.listing_count,
            item.query,
        ),
    )

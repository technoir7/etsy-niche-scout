from niche_scout.config import load_scoring
from niche_scout.schemas import KeywordFeatures
from niche_scout.scoring import score_keyword


def build_feature(
    query: str,
    result_count_estimate: int,
    median_price: float,
    mean_price: float,
    median_review_count: float,
    bestseller_count: int,
    share_low_review: float,
    title_similarity_concentration: float,
    dominant_shop_share: float,
    keyword_title_shares: dict[str, float],
) -> KeywordFeatures:
    return KeywordFeatures(
        query=query,
        normalized_query=query,
        seed_query=query,
        result_count_estimate=result_count_estimate,
        result_count_text=str(result_count_estimate),
        listing_count=24,
        median_price=median_price,
        mean_price=mean_price,
        median_review_count=median_review_count,
        max_review_count=int(median_review_count * 2),
        bestseller_count=bestseller_count,
        digital_share=0.9,
        share_low_review=share_low_review,
        title_similarity_concentration=title_similarity_concentration,
        dominant_shop_share=dominant_shop_share,
        keyword_title_shares=keyword_title_shares,
        distinct_shop_count=18,
        titles=[],
        shops=[],
        listing_urls=[],
    )


def test_scoring_favors_operational_buyer_intent_keywords() -> None:
    scoring = load_scoring()
    strong = build_feature(
        query="realtor intake form",
        result_count_estimate=1800,
        median_price=19.0,
        mean_price=18.5,
        median_review_count=80,
        bestseller_count=3,
        share_low_review=0.45,
        title_similarity_concentration=58.0,
        dominant_shop_share=0.16,
        keyword_title_shares={"editable": 0.2, "canva": 0.15, "bundle": 0.1, "template": 0.7},
    )
    weak = build_feature(
        query="wall art printable",
        result_count_estimate=55000,
        median_price=3.5,
        mean_price=4.0,
        median_review_count=300,
        bestseller_count=6,
        share_low_review=0.05,
        title_similarity_concentration=94.0,
        dominant_shop_share=0.48,
        keyword_title_shares={"editable": 0.0, "canva": 0.0, "bundle": 0.02, "template": 0.05},
    )

    strong_score = score_keyword(strong, scoring)
    weak_score = score_keyword(weak, scoring)

    assert strong_score.total_score > weak_score.total_score
    assert weak_score.saturation_penalty > strong_score.saturation_penalty


def test_scoring_uses_configured_signal_weights() -> None:
    scoring = load_scoring()
    feature = build_feature(
        query="realtor intake form editable",
        result_count_estimate=2000,
        median_price=18.0,
        mean_price=18.0,
        median_review_count=50,
        bestseller_count=1,
        share_low_review=0.4,
        title_similarity_concentration=60.0,
        dominant_shop_share=0.2,
        keyword_title_shares={"editable": 0.2, "canva": 0.0, "bundle": 0.0, "template": 0.2},
    )

    default_score = score_keyword(feature, scoring)
    lower_signal_scoring = scoring.model_copy(
        deep=True,
        update={
            "signal_weights": scoring.signal_weights.model_copy(
                update={
                    "buyer_intent_hit": 5.0,
                    "positive_modifier_hit": 1.0,
                    "positive_title_share": 5.0,
                    "negative_modifier_hit": 5.0,
                }
            )
        },
    )
    lower_signal_score = score_keyword(feature, lower_signal_scoring)

    assert default_score.buyer_intent_score > lower_signal_score.buyer_intent_score

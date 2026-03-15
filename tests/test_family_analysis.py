from niche_scout.family_analysis import analyze_family
from niche_scout.schemas import EnrichedKeywordRecord, KeywordFeatures, MetricsMergeContext, ScoreBreakdown


def build_record(query: str, product_type: str) -> EnrichedKeywordRecord:
    return EnrichedKeywordRecord(
        query=query,
        normalized_query=query,
        cluster_id="real-estate",
        cluster_label="real estate intake form",
        features=KeywordFeatures(
            query=query,
            normalized_query=query,
            share_low_review=0.45,
            digital_share=1.0,
            keyword_title_shares={"bundle": 0.2},
        ),
        score=ScoreBreakdown(
            buyer_intent_score=70,
            accessibility_score=62,
            monetization_score=68,
            proof_of_sales_score=59,
            differentiation_score=60,
            saturation_penalty=15,
            external_metrics_score=10,
            total_score=64,
            blended_score=66,
        ),
        canonical_profession="real estate",
        canonical_product_type=product_type,
        metrics_context=MetricsMergeContext(external_metrics_score=12),
    )


def test_analyze_family_scores_width_and_bundle_potential() -> None:
    family = analyze_family(
        "real-estate",
        "real estate intake form",
        [
            build_record("realtor intake form", "intake form"),
            build_record("real estate buyer intake form", "intake form"),
            build_record("realtor onboarding checklist", "checklist"),
        ],
    )
    assert family.family_width == 3
    assert family.bundle_potential_score > 50
    assert family.family_type in {"quick test", "scalable family", "monitor"}

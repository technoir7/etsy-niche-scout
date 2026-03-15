import json
from pathlib import Path

from niche_scout.config import load_clustering, load_defaults, load_scoring
from niche_scout.main import rank_scan_payload
from niche_scout.recommender import build_recommendation
from niche_scout.schemas import EnrichedKeywordRecord, KeywordFeatures, RankedPayload, ScanPayload, ScoreBreakdown


def test_zero_listing_keyword_produces_warning() -> None:
    scoring = load_scoring()
    clustering = load_clustering()
    item = EnrichedKeywordRecord(
        query="realtor intake form",
        normalized_query="realtor intake form",
        cluster_id="real-estate-intake",
        cluster_label="real estate intake form",
        features=KeywordFeatures(query="realtor intake form", normalized_query="realtor intake form", listing_count=0),
        score=ScoreBreakdown(
            buyer_intent_score=60,
            accessibility_score=60,
            monetization_score=60,
            proof_of_sales_score=0,
            differentiation_score=60,
            saturation_penalty=10,
            total_score=52,
            blended_score=52,
        ),
        canonical_profession="real estate",
        canonical_product_type="intake form",
    )

    recommendation = build_recommendation(item, [item], None, scoring, clustering)

    assert recommendation is not None
    assert any("No listing data was collected" in warning for warning in recommendation.warnings)
    assert recommendation.niche_label == "standalone"


def test_rank_scan_payload_populates_recommended_product_stack() -> None:
    fixture = Path("tests/fixtures/sample_scan.json").read_text(encoding="utf-8")
    payload = ScanPayload.model_validate(json.loads(fixture))

    ranked = rank_scan_payload(payload, load_defaults(), load_scoring(), load_clustering())

    assert ranked.families
    assert ranked.families[0].recommended_product_stack


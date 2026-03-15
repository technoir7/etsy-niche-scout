from niche_scout.clustering import canonicalize_keyword
from niche_scout.config import load_clustering, load_defaults, load_importers, load_scoring
from niche_scout.importers import attach_external_metrics, import_metrics_csv
from niche_scout.schemas import (
    EnrichedKeywordRecord,
    KeywordFeatures,
    RankedPayload,
    ScoreBreakdown,
)


def build_record(query: str, cluster_id: str = "real-estate-buyer-intake-form") -> EnrichedKeywordRecord:
    defaults = load_defaults()
    clustering = load_clustering()
    canonical = canonicalize_keyword(query, defaults, clustering)
    return EnrichedKeywordRecord(
        query=query,
        normalized_query=query,
        cluster_id=cluster_id,
        cluster_label="real estate buyer intake form",
        features=KeywordFeatures(query=query, normalized_query=query),
        score=ScoreBreakdown(
            buyer_intent_score=70,
            accessibility_score=60,
            monetization_score=65,
            proof_of_sales_score=55,
            differentiation_score=58,
            saturation_penalty=18,
            external_metrics_score=0,
            total_score=61,
            blended_score=61,
        ),
        canonical_profession=canonical.profession,
        canonical_product_type=canonical.product_type,
        canonical_core=list(canonical.core_tokens),
    )


def test_import_metrics_csv_handles_messy_erank_headers() -> None:
    metrics = import_metrics_csv("tests/fixtures/erank_sample.csv", "erank", load_importers())
    assert len(metrics) == 2
    assert metrics[0].normalized_keyword == "realtor intake form"
    assert metrics[0].search_volume == 1200.0
    assert metrics[0].ctr == 3.4


def test_import_metrics_csv_handles_bom_keyword_header(tmp_path) -> None:
    csv_path = tmp_path / "bom-erank.csv"
    csv_path.write_text(
        "\ufeffKeyword Phrase,Search Volume,Clicks,CTR,Competition,Trend,Average Price\n"
        "realtor intake form,1200,540,3.4,40,7,18\n",
        encoding="utf-8",
    )

    metrics = import_metrics_csv(csv_path, "erank", load_importers())

    assert len(metrics) == 1
    assert metrics[0].keyword == "realtor intake form"


def test_attach_external_metrics_uses_canonical_fallback_match() -> None:
    payload = RankedPayload(
        run_id="baseline",
        generated_at="2026-03-15T18:00:00Z",
        seeds=["realtor template"],
        ranked_keywords=[build_record("real estate buyer intake form")],
    )
    metrics = import_metrics_csv("tests/fixtures/erank_sample.csv", "erank", load_importers())
    enriched = attach_external_metrics(payload, metrics, load_defaults(), load_clustering(), load_scoring())
    record = enriched.ranked_keywords[0]
    assert record.metrics_context.search_volume == 1200.0
    assert record.metrics_context.match_strategy == "family_fuzzy"
    assert record.metrics_context.match_confidence >= 0.62
    assert record.score.blended_score and record.score.blended_score > record.score.total_score

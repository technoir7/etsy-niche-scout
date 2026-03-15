from datetime import UTC, datetime

from niche_scout.exporters import export_comparison_csv, families_to_dataframe
from niche_scout.schemas import KeywordChange, KeywordFamily, RankedPayload, RunComparison


def test_families_to_dataframe_serializes_lists_readably() -> None:
    payload = RankedPayload(
        run_id="test",
        generated_at=datetime.now(UTC),
        seeds=["realtor template"],
        ranked_keywords=[],
        families=[
            KeywordFamily(
                cluster_id="real-estate",
                cluster_name="real estate intake form",
                keywords=["realtor intake form", "buyer questionnaire realtor"],
                avg_score=60,
                max_score=70,
                family_score=68,
                family_width=2,
                expansion_potential_score=65,
                bundle_potential_score=55,
                avg_monetization_score=61,
                avg_accessibility_score=63,
                launch_strategy="Start with a single wedge product.",
                family_type="quick test",
                recommended_product_stack=["realtor intake form", "buyer questionnaire realtor"],
                adjacent_expansions=["checklist"],
                rationale=["2 keywords in family", "bundle potential 55.0"],
            )
        ],
    )

    dataframe = families_to_dataframe(payload)

    assert dataframe.loc[0, "keywords"] == "realtor intake form, buyer questionnaire realtor"
    assert dataframe.loc[0, "recommended_product_stack"] == "realtor intake form, buyer questionnaire realtor"
    assert dataframe.loc[0, "adjacent_expansions"] == "checklist"
    assert dataframe.loc[0, "rationale"] == "2 keywords in family, bundle potential 55.0"


def test_export_comparison_csv_includes_new_and_removed_rows(tmp_path) -> None:
    comparison = RunComparison(
        baseline_run_id="a",
        comparison_run_id="b",
        changed_keywords=[
            KeywordChange(
                query="realtor intake form",
                baseline_score=60,
                comparison_score=68,
                score_delta=8,
            )
        ],
        new_keywords=["therapy notes template"],
        removed_keywords=["airbnb welcome book"],
    )

    output = tmp_path / "comparison.csv"
    export_comparison_csv(output, comparison)
    content = output.read_text(encoding="utf-8")

    assert "event_type" in content
    assert "new,therapy notes template" in content
    assert "removed,airbnb welcome book" in content

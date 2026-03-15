import pandas as pd

from niche_scout.comparison import compare_dataframes
from niche_scout.config import load_clustering


def test_compare_dataframes_detects_new_keywords_and_score_changes() -> None:
    baseline = pd.DataFrame(
        [
            {
                "query": "realtor intake form",
                "normalized_query": "realtor intake form",
                "cluster_id": "real-estate-intake",
                "blended_score": 61.0,
                "search_volume": 1200.0,
                "competition": 40.0,
            }
        ]
    )
    comparison = pd.DataFrame(
        [
            {
                "query": "realtor intake form",
                "normalized_query": "realtor intake form",
                "cluster_id": "real-estate-buyer-intake",
                "blended_score": 72.0,
                "search_volume": 1400.0,
                "competition": 28.0,
            },
            {
                "query": "therapy notes template",
                "normalized_query": "therapy notes template",
                "cluster_id": "therapy-notes",
                "blended_score": 63.0,
                "search_volume": 900.0,
                "competition": 25.0,
            },
        ]
    )
    result = compare_dataframes(baseline, comparison, ("baseline", "comparison"), load_clustering())
    assert len(result.changed_keywords) == 1
    assert result.changed_keywords[0].cluster_changed is True
    assert result.new_keywords == ["therapy notes template"]

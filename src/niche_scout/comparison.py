"""Historical run comparison utilities."""

from __future__ import annotations

import pandas as pd

from niche_scout.config import ClusteringConfig
from niche_scout.schemas import KeywordChange, RunComparison


def _score_for_row(row: pd.Series) -> float | None:
    for column in ("blended_score", "total_score"):
        if column in row and pd.notna(row[column]):
            return float(row[column])
    return None


def compare_dataframes(
    baseline: pd.DataFrame,
    comparison: pd.DataFrame,
    run_ids: tuple[str, str],
    clustering: ClusteringConfig,
) -> RunComparison:
    baseline_indexed = baseline.set_index("normalized_query", drop=False)
    comparison_indexed = comparison.set_index("normalized_query", drop=False)
    baseline_keys = set(baseline_indexed.index)
    comparison_keys = set(comparison_indexed.index)

    changed_keywords: list[KeywordChange] = []
    changed_clusters: list[KeywordChange] = []
    for key in sorted(baseline_keys.intersection(comparison_keys)):
        left = baseline_indexed.loc[key]
        right = comparison_indexed.loc[key]
        baseline_score = _score_for_row(left)
        comparison_score = _score_for_row(right)
        score_delta = None
        if baseline_score is not None and comparison_score is not None:
            score_delta = round(comparison_score - baseline_score, 2)
        search_volume_delta = None
        if "search_volume" in baseline_indexed.columns and "search_volume" in comparison_indexed.columns:
            left_volume = left.get("search_volume")
            right_volume = right.get("search_volume")
            if pd.notna(left_volume) and pd.notna(right_volume):
                search_volume_delta = round(float(right_volume) - float(left_volume), 2)
        competition_delta = None
        if "competition" in baseline_indexed.columns and "competition" in comparison_indexed.columns:
            left_comp = left.get("competition")
            right_comp = right.get("competition")
            if pd.notna(left_comp) and pd.notna(right_comp):
                competition_delta = round(float(right_comp) - float(left_comp), 2)

        cluster_changed = str(left.get("cluster_id", "")) != str(right.get("cluster_id", ""))
        metric_changed = (
            (search_volume_delta is not None and abs(search_volume_delta) >= clustering.thresholds.significant_metric_delta)
            or (competition_delta is not None and abs(competition_delta) >= clustering.thresholds.significant_metric_delta)
        )
        if cluster_changed or metric_changed or (
            score_delta is not None and abs(score_delta) >= clustering.thresholds.significant_score_delta
        ):
            change = KeywordChange(
                query=str(right.get("query") or left.get("query")),
                baseline_score=baseline_score,
                comparison_score=comparison_score,
                score_delta=score_delta,
                baseline_cluster_id=str(left.get("cluster_id", "")),
                comparison_cluster_id=str(right.get("cluster_id", "")),
                cluster_changed=cluster_changed,
                search_volume_delta=search_volume_delta,
                competition_delta=competition_delta,
            )
            changed_keywords.append(change)
            if cluster_changed:
                changed_clusters.append(change)

    return RunComparison(
        baseline_run_id=run_ids[0],
        comparison_run_id=run_ids[1],
        changed_keywords=sorted(
            changed_keywords,
            key=lambda item: abs(item.score_delta or 0.0),
            reverse=True,
        ),
        new_keywords=sorted(comparison_keys - baseline_keys),
        removed_keywords=sorted(baseline_keys - comparison_keys),
        changed_clusters=changed_clusters,
    )

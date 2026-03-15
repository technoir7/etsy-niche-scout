"""Cluster-level family analysis and scoring."""

from __future__ import annotations

from statistics import mean

from niche_scout.schemas import EnrichedKeywordRecord, KeywordFamily


def _avg(values: list[float]) -> float:
    return round(mean(values), 2) if values else 0.0


def _family_type(avg_score: float, family_width: int, expansion_score: float) -> str:
    if avg_score >= 68 and family_width >= 3 and expansion_score >= 60:
        return "scalable family"
    if avg_score >= 58 and family_width <= 2:
        return "quick test"
    if avg_score >= 50:
        return "monitor"
    return "avoid"


def analyze_family(cluster_id: str, cluster_name: str, members: list[EnrichedKeywordRecord]) -> KeywordFamily:
    member_scores = [item.score.blended_score or item.score.total_score for item in members]
    monetization_scores = [item.score.monetization_score for item in members]
    accessibility_scores = [item.score.accessibility_score for item in members]
    external_scores = [item.metrics_context.external_metrics_score for item in members]
    product_types = {item.canonical_product_type for item in members if item.canonical_product_type}
    low_review_share = _avg([item.features.share_low_review * 100 for item in members])
    digital_share = _avg([item.features.digital_share * 100 for item in members])
    width = len(members)

    expansion_potential = min(
        100.0,
        width * 18
        + len(product_types) * 12
        + low_review_share * 0.25
        + max(_avg(external_scores), 0) * 0.20,
    )
    bundle_potential = min(
        100.0,
        width * 15
        + len(product_types) * 18
        + digital_share * 0.20
        + sum(item.features.keyword_title_shares.get("bundle", 0.0) * 100 for item in members) / max(width, 1) * 0.20,
    )
    family_score = round(
        min(
            100.0,
            _avg(member_scores) * 0.45
            + max(member_scores, default=0.0) * 0.20
            + expansion_potential * 0.20
            + bundle_potential * 0.15,
        ),
        2,
    )
    family_type = _family_type(_avg(member_scores), width, expansion_potential)
    launch_strategy = (
        "Start with a small family and ladder adjacent workflow docs."
        if family_type == "scalable family"
        else "Launch a single wedge product, then expand if CTR and saves look healthy."
        if family_type == "quick test"
        else "Track this family for better access or stronger external demand."
        if family_type == "monitor"
        else "Avoid launch until competition or positioning changes."
    )

    recommended_stack = [
        (member.recommendation.first_product if member.recommendation else member.query)
        for member in members
    ][:3]
    adjacent = sorted(
        {
            product
            for product in product_types
            if product and product != (members[0].canonical_product_type or "")
        }
    )[:4]
    rationale = [
        f"{width} keywords in family",
        f"avg keyword score {_avg(member_scores):.1f}",
        f"bundle potential {bundle_potential:.1f}",
        f"expansion potential {expansion_potential:.1f}",
    ]

    return KeywordFamily(
        cluster_id=cluster_id,
        cluster_name=cluster_name,
        keywords=[member.query for member in members],
        avg_score=_avg(member_scores),
        max_score=round(max(member_scores, default=0.0), 2),
        family_score=family_score,
        family_width=width,
        expansion_potential_score=round(expansion_potential, 2),
        bundle_potential_score=round(bundle_potential, 2),
        avg_monetization_score=_avg(monetization_scores),
        avg_accessibility_score=_avg(accessibility_scores),
        avg_external_metrics_score=_avg(external_scores),
        launch_strategy=launch_strategy,
        family_type=family_type,
        recommended_product_stack=recommended_stack,
        adjacent_expansions=adjacent,
        rationale=rationale,
    )


def analyze_families(grouped: dict[str, list[EnrichedKeywordRecord]]) -> list[KeywordFamily]:
    families = [
        analyze_family(cluster_id, members[0].cluster_label, members)
        for cluster_id, members in grouped.items()
        if members
    ]
    return sorted(families, key=lambda item: item.family_score, reverse=True)

"""Explainable keyword clustering around professions, product types, and core terms."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import logging
import re

from rapidfuzz.fuzz import token_set_ratio

from niche_scout.config import ClusteringConfig, DefaultsConfig
from niche_scout.schemas import KeywordFeatures
from niche_scout.utils import normalize_text, tokenize

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CanonicalKeyword:
    normalized_query: str
    profession: str | None
    product_type: str | None
    core_tokens: tuple[str, ...]


def _matched_alias_phrases(query: str, alias_map: dict[str, str]) -> list[tuple[str, str]]:
    lowered = normalize_text(query)
    found: list[tuple[str, str]] = []
    for phrase in sorted(alias_map, key=len, reverse=True):
        if phrase in lowered:
            canonical = alias_map[phrase]
            if (phrase, canonical) not in found:
                found.append((phrase, canonical))
    return found


def canonicalize_keyword(
    query: str,
    defaults: DefaultsConfig,
    clustering: ClusteringConfig,
) -> CanonicalKeyword:
    normalized = normalize_text(query)
    profession_matches = _matched_alias_phrases(normalized, clustering.lexicon.profession_aliases)
    product_matches = _matched_alias_phrases(normalized, clustering.lexicon.product_aliases)
    profession_hits = [canonical for _phrase, canonical in profession_matches]
    product_hits = [canonical for _phrase, canonical in product_matches]
    stripped = normalized
    for phrase, _canonical in profession_matches + product_matches:
        stripped = re.sub(rf"\b{re.escape(phrase)}\b", " ", stripped)
    stopwords = set(defaults.expansion.stopwords + defaults.expansion.intent_tokens + clustering.lexicon.stopwords)
    filler = set(clustering.lexicon.filler_tokens)
    core_tokens = tuple(
        sorted(
            {
                token
                for token in tokenize(stripped)
                if token not in stopwords and token not in filler
            }
        )
    )
    return CanonicalKeyword(
        normalized_query=normalized,
        profession=profession_hits[0] if profession_hits else None,
        product_type=product_hits[0] if product_hits else None,
        core_tokens=core_tokens,
    )


def jaccard_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left.intersection(right)) / len(left.union(right))


def should_cluster(
    left: CanonicalKeyword,
    right: CanonicalKeyword,
    clustering: ClusteringConfig,
) -> bool:
    left_core = set(left.core_tokens)
    right_core = set(right.core_tokens)
    profession_match = left.profession and left.profession == right.profession
    product_match = left.product_type and left.product_type == right.product_type
    core_overlap = len(left_core.intersection(right_core))
    duplicate_similarity = token_set_ratio(left.normalized_query, right.normalized_query)

    if duplicate_similarity >= clustering.thresholds.duplicate_similarity:
        return True
    if profession_match and product_match and core_overlap >= clustering.thresholds.min_core_overlap:
        return True
    if profession_match and product_match and (not left_core or not right_core):
        return True
    if profession_match and duplicate_similarity >= clustering.thresholds.family_similarity:
        return True
    if product_match and core_overlap >= max(1, clustering.thresholds.min_core_overlap):
        return True
    return jaccard_similarity(left_core, right_core) >= 0.6 and duplicate_similarity >= clustering.thresholds.family_similarity


def cluster_label(items: list[KeywordFeatures], defaults: DefaultsConfig, clustering: ClusteringConfig) -> str:
    canonicals = [canonicalize_keyword(item.query, defaults, clustering) for item in items]
    professions = Counter(c.profession for c in canonicals if c.profession)
    product_types = Counter(c.product_type for c in canonicals if c.product_type)
    core_tokens: Counter[str] = Counter()
    for canonical in canonicals:
        core_tokens.update(canonical.core_tokens)

    parts: list[str] = []
    if professions:
        parts.append(professions.most_common(1)[0][0])
    if core_tokens:
        parts.extend(token for token, _count in core_tokens.most_common(2) if token not in parts)
    if product_types:
        product = product_types.most_common(1)[0][0]
        if product not in parts:
            parts.append(product)
    return " ".join(parts[:4]) if parts else items[0].normalized_query


def cluster_keywords(
    features: list[KeywordFeatures],
    defaults: DefaultsConfig,
    clustering: ClusteringConfig,
) -> tuple[dict[str, list[KeywordFeatures]], dict[str, CanonicalKeyword]]:
    if len(features) > clustering.thresholds.scale_warning_threshold:
        logger.warning(
            "Clustering %s keywords with pairwise matching; this path is O(n^2) and may slow down.",
            len(features),
        )
    parent = {item.normalized_query: item.normalized_query for item in features}
    canonical_lookup = {
        item.normalized_query: canonicalize_keyword(item.query, defaults, clustering)
        for item in features
    }

    def find(node: str) -> str:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for index, left in enumerate(features):
        for right in features[index + 1 :]:
            if should_cluster(
                canonical_lookup[left.normalized_query],
                canonical_lookup[right.normalized_query],
                clustering,
            ):
                union(left.normalized_query, right.normalized_query)

    grouped: dict[str, list[KeywordFeatures]] = defaultdict(list)
    for item in features:
        grouped[find(item.normalized_query)].append(item)
    return grouped, canonical_lookup

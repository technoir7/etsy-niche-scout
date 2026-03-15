"""Rule-based keyword expansion tuned for digital-product niches."""

from __future__ import annotations

from collections import OrderedDict
import re

from niche_scout.config import ExpansionConfig
from niche_scout.utils import normalize_text, tokenize


def strip_intent_tokens(seed: str, config: ExpansionConfig) -> str:
    cleaned = normalize_text(seed)
    removable = sorted(config.intent_tokens + config.strip_tokens, key=len, reverse=True)
    for phrase in removable:
        cleaned = re.sub(rf"\b{re.escape(phrase)}\b", " ", cleaned)
    tokens = tokenize(cleaned)
    return " ".join(tokens).strip() or normalize_text(seed)


def synonym_variants(seed: str, config: ExpansionConfig) -> list[str]:
    variants: "OrderedDict[str, None]" = OrderedDict()
    variants[normalize_text(seed)] = None
    for phrase, replacements in config.synonym_map.items():
        if phrase in seed.lower():
            for replacement in replacements:
                variants[normalize_text(seed.lower().replace(phrase, replacement))] = None
    return list(variants.keys())


def expand_seed(seed: str, config: ExpansionConfig) -> list[str]:
    normalized_seed = normalize_text(seed)
    core = strip_intent_tokens(normalized_seed, config)
    variants = synonym_variants(normalized_seed, config)
    results: "OrderedDict[str, None]" = OrderedDict()

    def add(candidate: str) -> None:
        cleaned = normalize_text(candidate)
        if cleaned:
            results.setdefault(cleaned, None)

    add(normalized_seed)
    add(core)

    base_variants: list[str] = []
    for variant in variants:
        base_variant = strip_intent_tokens(variant, config)
        add(base_variant)
        base_variants.append(base_variant)

    for intent in config.intent_tokens:
        for base_variant in base_variants:
            add(f"{base_variant} {intent}")

    for modifier in config.modifiers:
        for base_variant in base_variants:
            add(f"{base_variant} {modifier} template")
            add(f"{base_variant} {modifier} bundle")

    return list(results.keys())[: config.max_candidates_per_seed]


def expand_keywords(seeds: list[str], config: ExpansionConfig) -> list[str]:
    combined: "OrderedDict[str, None]" = OrderedDict()
    for seed in seeds:
        for candidate in expand_seed(seed, config):
            combined.setdefault(candidate, None)
    return list(combined.keys())


def expand_keywords_with_seeds(seeds: list[str], config: ExpansionConfig) -> dict[str, str]:
    combined: "OrderedDict[str, str]" = OrderedDict()
    for seed in seeds:
        for candidate in expand_seed(seed, config):
            combined.setdefault(candidate, seed)
    return dict(combined)

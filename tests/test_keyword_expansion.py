from niche_scout.config import load_defaults
from niche_scout.keyword_expansion import expand_keywords_with_seeds, expand_seed, strip_intent_tokens


def test_strip_intent_tokens_removes_product_words() -> None:
    config = load_defaults().expansion
    assert strip_intent_tokens("realtor template", config) == "realtor"


def test_expand_seed_generates_professional_variants() -> None:
    config = load_defaults().expansion
    expanded = expand_seed("realtor template", config)
    assert "realtor intake form" in expanded
    assert "real estate buyer questionnaire" in expanded


def test_expand_keywords_with_seeds_preserves_seed_mapping() -> None:
    config = load_defaults().expansion
    mapping = expand_keywords_with_seeds(["therapy notes"], config)
    assert mapping["therapy notes"] == "therapy notes"
    assert "therapist notes template" in mapping

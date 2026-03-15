from niche_scout.clustering import canonicalize_keyword, cluster_keywords
from niche_scout.config import load_clustering, load_defaults
from niche_scout.schemas import KeywordFeatures


def build_feature(query: str) -> KeywordFeatures:
    return KeywordFeatures(query=query, normalized_query=query)


def test_canonicalize_keyword_groups_profession_and_product_type() -> None:
    defaults = load_defaults()
    clustering = load_clustering()
    canonical = canonicalize_keyword("buyer questionnaire realtor", defaults, clustering)
    assert canonical.profession == "real estate"
    assert canonical.product_type == "intake form"


def test_cluster_keywords_groups_launchable_family_terms() -> None:
    defaults = load_defaults()
    clustering = load_clustering()
    features = [
        build_feature("realtor intake form"),
        build_feature("real estate buyer intake form"),
        build_feature("buyer questionnaire realtor"),
        build_feature("therapy notes template"),
    ]
    grouped, _canonical_lookup = cluster_keywords(features, defaults, clustering)
    cluster_sizes = sorted(len(members) for members in grouped.values())
    assert cluster_sizes == [1, 3]

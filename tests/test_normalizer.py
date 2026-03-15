from datetime import UTC, datetime
from pathlib import Path

from niche_scout.config import load_scoring
from niche_scout.listing_extractor import (
    extract_search_page_from_html,
    parse_count_text,
    parse_listing_blob,
    parse_price_text,
    parse_rating_text,
    parse_result_count_blob,
)
from niche_scout.normalizer import normalize_search_result
from niche_scout.schemas import ListingSignal, SearchResultPage


def test_parsing_helpers_handle_common_marketplace_text() -> None:
    assert parse_count_text("12,345 results") == 12345
    assert parse_price_text("$12.50") == (12.5, "$")
    assert parse_rating_text("Rated 4.9 out of 5 stars") == 4.9
    assert parse_result_count_blob("Showing 1-24 of 12,345 results for therapy notes") == ("12,345 results", 12345)
    blob = parse_listing_blob("Editable Canva template $18.00 42 reviews instant download")
    assert blob["price"] == 18.0
    assert blob["review_count"] == 42
    assert blob["digital_product"] is True


def test_normalize_search_result_aggregates_listing_features() -> None:
    scoring = load_scoring()
    result = SearchResultPage(
        query="therapy notes",
        normalized_query="therapy notes",
        seed_query="therapy notes",
        search_url="https://www.etsy.com/search?q=therapy+notes",
        result_count_text="1,234 results",
        parsed_result_count=1234,
        fetched_at=datetime.now(UTC),
        listings=[
            ListingSignal(
                query="therapy notes",
                title="therapy notes editable template",
                price=14.0,
                currency="$",
                review_count=12,
                star_rating=4.8,
                shop_name="note studio",
                bestseller=False,
                digital_product=True,
                listing_url="https://etsy.com/listing/1",
                rank_position=1,
            ),
            ListingSignal(
                query="therapy notes",
                title="therapy notes canva bundle",
                price=22.0,
                currency="$",
                review_count=220,
                star_rating=4.9,
                shop_name="note studio",
                bestseller=True,
                digital_product=True,
                listing_url="https://etsy.com/listing/2",
                rank_position=2,
            ),
            ListingSignal(
                query="therapy notes",
                title="soap notes worksheet for counselors",
                price=18.0,
                currency="$",
                review_count=4,
                star_rating=4.6,
                shop_name="care ops",
                bestseller=False,
                digital_product=True,
                listing_url="https://etsy.com/listing/3",
                rank_position=3,
            ),
        ],
    )

    features = normalize_search_result(result, scoring)

    assert features.result_count_estimate == 1234
    assert features.median_price == 18.0
    assert round(features.mean_price or 0, 2) == 18.0
    assert features.bestseller_count == 1
    assert features.distinct_shop_count == 2
    assert features.share_low_review == round(2 / 3, 3)
    assert features.keyword_title_shares["editable"] == round(1 / 3, 3)


def test_extract_search_page_from_html_fixture() -> None:
    html = Path("tests/fixtures/etsy_search_fragment.html").read_text(encoding="utf-8")
    extracted = extract_search_page_from_html(html, "therapy notes", top_n=5)
    assert extracted["parsed_result_count"] == 12345
    assert len(extracted["listings"]) == 2
    assert extracted["listings"][0].listing_url == "https://www.etsy.com/listing/123456789/therapy-notes-template"
    assert extracted["listings"][0].price == 18.0

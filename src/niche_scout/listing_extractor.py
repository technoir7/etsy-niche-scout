"""Extract Etsy search page signals using configurable selectors."""

from __future__ import annotations

import re
from html import unescape
from collections.abc import Iterable
from typing import Any
from urllib.parse import urljoin

from playwright.sync_api import Locator, Page

from niche_scout.config import SelectorsConfig
from niche_scout.schemas import ListingSignal
from niche_scout.utils import normalize_text


PRICE_RE = re.compile(r"([€$£])?\s*([0-9]+(?:[.,][0-9]{2})?)")
COUNT_RE = re.compile(r"([0-9][0-9,\.]*)")
RATING_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)")
RESULT_COUNT_RE = re.compile(r"([0-9][0-9,]*)\s+results", re.IGNORECASE)
PRICE_IN_BLOB_RE = re.compile(r"([€$£])\s*([0-9]+(?:\.[0-9]{2})?)")
REVIEWS_IN_BLOB_RE = re.compile(r"([0-9][0-9,]*)\s+reviews?", re.IGNORECASE)
DIGITAL_MARKERS = ("digital", "instant download", "pdf", "template", "canva")
TAG_RE = re.compile(r"<[^>]+>")
LISTING_LINK_RE = re.compile(r"""<a[^>]+href=["']([^"']*/listing/[^"']+)["'][^>]*>(.*?)</a>""", re.IGNORECASE | re.DOTALL)
IMAGE_RE = re.compile(r"""<img[^>]+src=["']([^"']+)["']""", re.IGNORECASE)
RATING_IN_BLOB_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*(?:out of 5 stars|star rating)", re.IGNORECASE)
BESTSELLER_RE = re.compile(r"\bbestseller\b", re.IGNORECASE)


def first_text(locator: Locator, selectors: Iterable[str]) -> str | None:
    for selector in selectors:
        node = locator.locator(selector).first
        if node.count():
            text = safe_inner_text(node)
            if text:
                return text
    return None


def first_attr(locator: Locator, selectors: Iterable[str], attr: str) -> str | None:
    for selector in selectors:
        node = locator.locator(selector).first
        if node.count():
            value = node.get_attribute(attr, timeout=1_500)
            if value:
                return value
    return None


def safe_inner_text(locator: Locator) -> str | None:
    try:
        text = locator.inner_text(timeout=1_500).strip()
        return text or None
    except Exception:
        return None


def parse_price_text(value: str | None) -> tuple[float | None, str | None]:
    if not value:
        return None, None
    match = PRICE_RE.search(value.replace(",", ""))
    if not match:
        return None, None
    currency, amount = match.groups()
    return float(amount), currency or "$"


def parse_count_text(value: str | None) -> int | None:
    if not value:
        return None
    match = COUNT_RE.search(value.replace(".", ""))
    if not match:
        return None
    raw = match.group(1).replace(",", "")
    try:
        return int(raw)
    except ValueError:
        return None


def parse_rating_text(value: str | None) -> float | None:
    if not value:
        return None
    match = RATING_RE.search(value)
    if not match:
        return None
    return float(match.group(1))


def parse_result_count_blob(value: str | None) -> tuple[str | None, int | None]:
    if not value:
        return None, None
    match = RESULT_COUNT_RE.search(value)
    if not match:
        return None, None
    count_text = match.group(0)
    return count_text, parse_count_text(match.group(1))


def parse_listing_blob(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    price_match = PRICE_IN_BLOB_RE.search(value)
    reviews_match = REVIEWS_IN_BLOB_RE.search(value)
    rating_match = RATING_IN_BLOB_RE.search(value)
    return {
        "price": float(price_match.group(2)) if price_match else None,
        "currency": price_match.group(1) if price_match else None,
        "review_count": parse_count_text(reviews_match.group(1)) if reviews_match else None,
        "star_rating": float(rating_match.group(1)) if rating_match else None,
        "digital_product": any(marker in value.lower() for marker in DIGITAL_MARKERS),
        "bestseller": bool(BESTSELLER_RE.search(value)),
    }


def html_to_text(value: str) -> str:
    return normalize_text(unescape(TAG_RE.sub(" ", value)))


def extract_listing_cards_from_html(
    html: str,
    query: str,
    top_n: int,
    base_url: str = "https://www.etsy.com",
) -> list[ListingSignal]:
    cards: list[ListingSignal] = []
    seen_urls: set[str] = set()
    for index, match in enumerate(LISTING_LINK_RE.finditer(html), start=1):
        if len(cards) >= top_n:
            break
        listing_url = urljoin(base_url, match.group(1))
        if listing_url in seen_urls:
            continue
        seen_urls.add(listing_url)
        # Fallback HTML extraction assumes price/review badges are rendered near
        # the listing anchor in the cached markup. The byte window is brittle but
        # keeps this parser simple and debug-friendly when selector extraction fails.
        segment = html[max(0, match.start() - 500) : min(len(html), match.end() + 1200)]
        segment_text = html_to_text(segment)
        link_text = html_to_text(match.group(2))
        if not link_text:
            continue
        blob = parse_listing_blob(segment_text)
        image_match = IMAGE_RE.search(segment)
        cards.append(
            ListingSignal(
                query=query,
                title=link_text,
                price=blob.get("price"),
                currency=blob.get("currency"),
                review_count=blob.get("review_count"),
                star_rating=blob.get("star_rating"),
                shop_name=None,
                bestseller=bool(blob.get("bestseller")),
                digital_product=bool(blob.get("digital_product")),
                listing_url=listing_url,
                image_url=image_match.group(1) if image_match else None,
                rank_position=index,
            )
        )
    return cards


def extract_result_count(page: Page, selectors: SelectorsConfig) -> tuple[str | None, int | None]:
    for selector in selectors.search.result_count:
        node = page.locator(selector).first
        if node.count():
            text = safe_inner_text(node)
            parsed = parse_count_text(text)
            if text:
                return text, parsed
    body_text = safe_inner_text(page.locator("body").first)
    return parse_result_count_blob(body_text)


def extract_listing_card(
    card: Locator,
    query: str,
    rank_position: int,
    selectors: SelectorsConfig,
    base_url: str = "https://www.etsy.com",
) -> ListingSignal:
    title = first_text(card, selectors.listing.title)
    price_text = first_text(card, selectors.listing.price)
    rating_text = first_text(card, selectors.listing.rating)
    reviews_text = first_text(card, selectors.listing.reviews)
    shop_name = first_text(card, selectors.listing.shop_name)
    listing_url = first_attr(card, selectors.listing.url, "href")
    image_url = first_attr(card, selectors.listing.image, "src")
    bestseller_text = first_text(card, selectors.listing.bestseller)
    digital_text = first_text(card, selectors.listing.digital)
    aria_rating = first_attr(card, selectors.listing.rating, "aria-label")
    reviews_label = first_attr(card, selectors.listing.reviews, "aria-label")
    blob = parse_listing_blob(safe_inner_text(card))

    price, currency = parse_price_text(price_text)
    price = price if price is not None else blob.get("price")
    currency = currency if currency is not None else blob.get("currency")
    rating = parse_rating_text(aria_rating or rating_text)
    review_count = parse_count_text(reviews_label or reviews_text)
    review_count = review_count if review_count is not None else blob.get("review_count")

    return ListingSignal(
        query=query,
        title=normalize_text(title) if title else None,
        price=price,
        currency=currency,
        review_count=review_count,
        star_rating=rating,
        shop_name=normalize_text(shop_name) if shop_name else None,
        bestseller=bool(bestseller_text and "best" in bestseller_text.lower()),
        digital_product=bool((digital_text and "digital" in digital_text.lower()) or blob.get("digital_product")),
        listing_url=urljoin(base_url, listing_url) if listing_url else None,
        image_url=image_url,
        rank_position=rank_position,
    )


def extract_listing_cards(
    page: Page,
    query: str,
    selectors: SelectorsConfig,
    top_n: int,
) -> list[ListingSignal]:
    cards: list[ListingSignal] = []
    locator = None
    for selector in selectors.search.listing_cards:
        candidate = page.locator(selector)
        if candidate.count():
            locator = candidate
            break
    if locator is None:
        return cards

    total = min(locator.count(), top_n)
    for index in range(total):
        try:
            cards.append(extract_listing_card(locator.nth(index), query, index + 1, selectors))
        except Exception:
            continue
    return cards


def extract_search_page(
    page: Page,
    query: str,
    selectors: SelectorsConfig,
    top_n: int,
) -> dict[str, Any]:
    result_count_text, parsed_result_count = extract_result_count(page, selectors)
    listings = extract_listing_cards(page, query, selectors, top_n)
    if not listings:
        html = page.content()
        fallback = extract_search_page_from_html(html, query, top_n)
        result_count_text = result_count_text or fallback["result_count_text"]
        parsed_result_count = parsed_result_count or fallback["parsed_result_count"]
        listings = fallback["listings"]
    return {
        "result_count_text": result_count_text,
        "parsed_result_count": parsed_result_count,
        "listings": listings,
    }


def extract_search_page_from_html(
    html: str,
    query: str,
    top_n: int,
) -> dict[str, Any]:
    body_text = html_to_text(html)
    result_count_text, parsed_result_count = parse_result_count_blob(body_text)
    listings = extract_listing_cards_from_html(html, query, top_n)
    return {
        "result_count_text": result_count_text,
        "parsed_result_count": parsed_result_count,
        "listings": listings,
    }

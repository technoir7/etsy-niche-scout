"""Collect Etsy first-page search signals for a set of queries."""

from __future__ import annotations

import logging
from pathlib import Path

from rich.progress import track

from niche_scout.config import ROOT_DIR, DefaultsConfig, SelectorsConfig
from niche_scout.etsy_client import EtsyClient
from niche_scout.listing_extractor import extract_search_page
from niche_scout.schemas import ScanPayload, SearchResultPage
from niche_scout.utils import ensure_dir, normalize_text, slugify, utc_now


logger = logging.getLogger(__name__)


class SerpCollector:
    def __init__(self, defaults: DefaultsConfig, selectors: SelectorsConfig) -> None:
        self.defaults = defaults
        self.selectors = selectors

    def collect(
        self,
        query_map: dict[str, str],
        top_n: int | None = None,
        use_cache: bool | None = None,
        refresh_cache: bool = False,
    ) -> ScanPayload:
        top_n = top_n or self.defaults.runtime.top_n
        screenshot_dir = ensure_dir(ROOT_DIR / self.defaults.paths.screenshot_dir)
        cache_dir = ensure_dir(ROOT_DIR / self.defaults.paths.html_cache_dir)
        use_cache = self.defaults.runtime.use_html_cache if use_cache is None else use_cache
        results: list[SearchResultPage] = []

        with EtsyClient(self.defaults) as client:
            page = client.new_page()
            for query, seed in track(query_map.items(), description="Scanning Etsy"):
                normalized = normalize_text(query)
                slug = slugify(query)
                cached_html_path = Path(cache_dir) / f"{slug}.html"
                try:
                    if use_cache and cached_html_path.exists() and not refresh_cache:
                        client.load_cached_html(page, cached_html_path)
                        search_url = client.build_search_url(query)
                    else:
                        search_url = client.search(page, query)
                        client.save_artifacts(page, html_path=cached_html_path)
                    extracted = extract_search_page(page, query, self.selectors, top_n=top_n)
                    result = SearchResultPage(
                        query=query,
                        normalized_query=normalized,
                        seed_query=seed,
                        search_url=search_url,
                        result_count_text=extracted["result_count_text"],
                        parsed_result_count=extracted["parsed_result_count"],
                        fetched_at=utc_now(),
                        listings=extracted["listings"],
                        raw_html_path=str(cached_html_path),
                    )
                except Exception as exc:
                    html_path = Path(screenshot_dir) / f"{slug}.html"
                    screenshot_path = Path(screenshot_dir) / f"{slug}.png"
                    try:
                        client.save_artifacts(page, html_path=html_path, screenshot_path=screenshot_path)
                    except Exception:
                        logger.exception("Failed to save failure artifacts for %s", query)
                    result = SearchResultPage(
                        query=query,
                        normalized_query=normalized,
                        seed_query=seed,
                        search_url=client.build_search_url(query),
                        fetched_at=utc_now(),
                        listings=[],
                        errors=[str(exc)],
                        raw_html_path=str(html_path),
                        screenshot_path=str(screenshot_path),
                    )
                results.append(result)

        return ScanPayload(
            generated_at=utc_now(),
            seeds=sorted(set(query_map.values())),
            expanded_queries=list(query_map.keys()),
            results=results,
        )

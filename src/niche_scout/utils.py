"""Shared utility helpers."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
MULTISPACE_RE = re.compile(r"\s+")


def utc_now() -> datetime:
    return datetime.now(UTC)


def slugify(value: str) -> str:
    collapsed = NON_ALNUM_RE.sub("-", value.lower()).strip("-")
    return collapsed or "untitled"


def normalize_text(value: str) -> str:
    cleaned = MULTISPACE_RE.sub(" ", value.strip().lower())
    return cleaned


def tokenize(value: str) -> list[str]:
    return [part for part in NON_ALNUM_RE.split(value.lower()) if part]


def normalize_header(value: str) -> str:
    sanitized = value.replace("\ufeff", "").lower()
    return normalize_text(NON_ALNUM_RE.sub(" ", sanitized))


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("%", "").replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def average_optional(values: list[float | None]) -> float | None:
    numbers = [value for value in values if value is not None]
    if not numbers:
        return None
    return sum(numbers) / len(numbers)


def ensure_dir(path: str | Path) -> Path:
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


def write_json(path: str | Path, payload: Any) -> Path:
    target = Path(path)
    ensure_dir(target.parent)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, default=str)
    return target


def read_json(path: str | Path) -> Any:
    with Path(path).open("r", encoding="utf-8") as handle:
        return json.load(handle)


def round_price_range(value: float | None) -> str:
    if value is None:
        return "$8-$18"
    lower = max(1, int(value // 2 * 2))
    upper = max(lower + 4, int((value + 4) // 2 * 2))
    return f"${lower}-${upper}"

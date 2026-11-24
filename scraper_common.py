from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Iterable, Mapping
from urllib.parse import urljoin


BASE_URL = "https://mitadmissions.org/blogs/"
FIELDNAMES = [
    "Title",
    "Author",
    "Comment Count",
    "Time",
    "Article Content",
    "Images In Article",
]


def normalize_text(value: str | None) -> str:
    """Collapse browser formatting whitespace while preserving readable paragraphs."""
    if not value:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def clean_article_text(value: str | None) -> str:
    """Remove empty lines and normalize whitespace within each article paragraph."""
    if not value:
        return ""
    lines = (normalize_text(line) for line in value.splitlines())
    return "\n".join(line for line in lines if line)


def parse_comment_count(value: str | None) -> str:
    """Return a numeric count, or N/A when Disqus did not provide a count."""
    normalized = normalize_text(value)
    match = re.search(r"\d[\d,]*", normalized)
    if not match:
        return "N/A"
    return match.group(0).replace(",", "")


def listing_url(page_number: int) -> str:
    if page_number < 1:
        raise ValueError("page_number must be at least 1")
    if page_number == 1:
        return BASE_URL
    return urljoin(BASE_URL, f"page/{page_number}/")


def absolute_url(value: str | None, base_url: str) -> str:
    if not value:
        return ""
    return urljoin(base_url, value)


def unique_urls(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value and value not in seen:
            seen.add(value)
            result.append(value)
    return result


def write_csv(rows: Iterable[Mapping[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    csv.field_size_limit(10 * 1024 * 1024)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES, quoting=csv.QUOTE_ALL)
        writer.writeheader()
        writer.writerows(rows)

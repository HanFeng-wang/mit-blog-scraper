from __future__ import annotations

import argparse
import os
import random
import time
from pathlib import Path
from urllib.parse import urlencode

from DrissionPage import ChromiumOptions, ChromiumPage

from scraper_common import (
    BASE_URL,
    absolute_url,
    clean_article_text,
    listing_url,
    normalize_text,
    parse_comment_count,
    unique_urls,
    write_csv,
)


DISQUS_COUNT_URL = "https://mitadmissions.disqus.com/count-data.js"
DISQUS_BATCH_SIZE = 10


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Crawl MIT Admissions blogs with DrissionPage."
    )
    parser.add_argument("--pages", type=int, default=1, help="Listing pages to crawl.")
    parser.add_argument("--limit", type=int, help="Maximum number of articles.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/drissionpage_blogs.csv"),
        help="CSV output path.",
    )
    parser.add_argument("--delay", type=float, default=0.5, help="Delay per article.")
    parser.add_argument(
        "--comment-timeout",
        type=float,
        default=8.0,
        help="Disqus count request timeout in seconds.",
    )
    parser.add_argument(
        "--timeout", type=float, default=60.0, help="Page timeout in seconds."
    )
    parser.add_argument("--headed", action="store_true", help="Show the browser.")
    parser.add_argument("--browser-path", help="Chrome/Edge executable path.")
    parser.add_argument(
        "--proxy",
        help="Proxy server URL, for example http://127.0.0.1:7892.",
    )
    args = parser.parse_args()
    if args.pages < 1:
        parser.error("--pages must be at least 1")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")
    if args.delay < 0:
        parser.error("--delay cannot be negative")
    return args


def default_browser_path() -> str | None:
    configured = os.environ.get("MIT_SCRAPER_BROWSER_PATH")
    candidates = [
        configured,
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    return next(
        (candidate for candidate in candidates if candidate and Path(candidate).is_file()),
        None,
    )


def build_page(args: argparse.Namespace) -> ChromiumPage:
    options = ChromiumOptions().headless(not args.headed)
    browser_path = args.browser_path or default_browser_path()
    if browser_path:
        options.set_browser_path(browser_path)
    if args.proxy:
        options.set_proxy(args.proxy)
    page = ChromiumPage(options)
    page.set.load_mode.eager()
    page.set.timeouts(
        base=min(args.timeout, 30),
        page_load=args.timeout,
        script=min(args.timeout, 30),
    )
    return page


def text_of(parent, selector: str) -> str:
    element = parent.ele(f"css:{selector}")
    return normalize_text(element.text) if element else ""


def attribute_of(parent, selector: str, attribute: str) -> str:
    element = parent.ele(f"css:{selector}")
    return element.attr(attribute) or "" if element else ""


def card_metadata(card) -> dict[str, str]:
    href = attribute_of(card, ".post-tease__h__link", "href")
    return {
        "title": text_of(card, ".post-tease__title"),
        "author": text_of(card, ".post-tease__meta-item--author a"),
        "time": text_of(card, ".tease__meta-item--date"),
        "comment_count": parse_comment_count(text_of(card, ".tease__comment-text")),
        "disqus_identifier": attribute_of(
            card, ".tease__comment-text a", "data-disqus-identifier"
        ),
        "url": absolute_url(href, BASE_URL),
    }


def load_disqus_counts(page, items: list[dict[str, str]], timeout_seconds: float) -> None:
    identifiers = list(
        dict.fromkeys(
            item["disqus_identifier"] for item in items if item["disqus_identifier"]
        )
    )
    if not identifiers:
        return

    print(f"  Loading Disqus counts for {len(identifiers)} articles")
    counts: dict[str, str] = {}
    for start in range(0, len(identifiers), DISQUS_BATCH_SIZE):
        batch = identifiers[start : start + DISQUS_BATCH_SIZE]
        count_url = f"{DISQUS_COUNT_URL}?{urlencode([('1', value) for value in batch])}"
        try:
            data = page.run_js(
                """
                return new Promise((resolve) => {
                    window.__mitDisqusCounts = null;
                    window.DISQUSWIDGETS = {
                        displayCount: (value) => {
                            window.__mitDisqusCounts = value;
                        }
                    };
                    const element = document.createElement('script');
                    element.src = arguments[0];
                    element.onload = () => resolve(window.__mitDisqusCounts);
                    element.onerror = () => resolve(null);
                    document.head.appendChild(element);
                });
                """,
                count_url,
                timeout=timeout_seconds,
            )
        except Exception as exc:
            print(f"  Disqus count request failed: {type(exc).__name__}: {exc}")
            continue

        for entry in (data or {}).get("counts", []):
            identifier = entry.get("id")
            comments = entry.get("comments")
            if identifier and comments is not None:
                counts[identifier] = str(comments)

    for item in items:
        if item["comment_count"] == "N/A":
            item["comment_count"] = counts.get(item["disqus_identifier"], "N/A")


def crawl(args: argparse.Namespace) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    page = build_page(args)
    try:
        for page_number in range(1, args.pages + 1):
            if args.limit is not None and len(rows) >= args.limit:
                break

            url = listing_url(page_number)
            print(f"Listing page {page_number}: {url}")
            page.get(
                url,
                retry=2,
                interval=1,
                timeout=args.timeout,
            )
            page.wait.doc_loaded(timeout=args.timeout)
            page.wait.ele_displayed("css:article.tease", timeout=args.timeout)

            cards = page.eles("css:article.tease")
            page_items = [card_metadata(card) for card in cards]
            if args.limit is not None:
                page_items = page_items[: args.limit - len(rows)]
            load_disqus_counts(page, page_items, args.comment_timeout)

            for item in page_items:
                print(f"  Article: {item['title']}")
                page.get(
                    item["url"],
                    retry=2,
                    interval=1,
                    timeout=args.timeout,
                )
                page.wait.doc_loaded(timeout=args.timeout)
                body = page.ele("css:.article__body")
                if not body:
                    raise RuntimeError(f"Article body not found: {item['url']}")

                content = clean_article_text(body.run_js("return this.innerText"))
                image_urls = unique_urls(
                    absolute_url(
                        image.attr("data-src") or image.attr("src"),
                        item["url"],
                    )
                    for image in body.eles("css:img")
                )
                rows.append(
                    {
                        "Title": item["title"],
                        "Author": item["author"],
                        "Comment Count": item["comment_count"],
                        "Time": item["time"],
                        "Article Content": content,
                        "Images In Article": "\n".join(image_urls),
                    }
                )
                if args.delay:
                    time.sleep(args.delay + random.uniform(0, 0.2))
    finally:
        page.quit()

    return rows


def main() -> None:
    args = parse_args()
    rows = crawl(args)
    write_csv(rows, args.output)
    print(f"Saved {len(rows)} rows to {args.output.resolve()}")


if __name__ == "__main__":
    main()

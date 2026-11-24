from __future__ import annotations

import argparse
import random
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Crawl MIT Admissions blogs with Playwright."
    )
    parser.add_argument("--pages", type=int, default=1, help="Listing pages to crawl.")
    parser.add_argument("--limit", type=int, help="Maximum number of articles.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("output/playwright_blogs.csv"),
        help="CSV output path.",
    )
    parser.add_argument("--delay", type=float, default=0.5, help="Delay per article.")
    parser.add_argument(
        "--comment-timeout", type=float, default=8.0, help="Disqus wait in seconds."
    )
    parser.add_argument(
        "--timeout", type=float, default=60.0, help="Page timeout in seconds."
    )
    parser.add_argument("--headed", action="store_true", help="Show the browser.")
    parser.add_argument(
        "--channel",
        default="chrome",
        help="Playwright browser channel; use an empty value for bundled Chromium.",
    )
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


def launch_browser(playwright: Any, args: argparse.Namespace) -> Any:
    launch_options = {"headless": not args.headed}
    if args.proxy:
        launch_options["proxy"] = {"server": args.proxy}
    if args.channel:
        try:
            return playwright.chromium.launch(channel=args.channel, **launch_options)
        except PlaywrightError as exc:
            print(
                f"Could not launch channel {args.channel!r}; trying bundled Chromium: {exc}"
            )
    return playwright.chromium.launch(**launch_options)


def wait_for_disqus(page: Any, timeout_seconds: float) -> None:
    try:
        page.wait_for_function(
            """
            () => Array.from(document.querySelectorAll('.tease__comment-text'))
                .some((element) => element.textContent.trim().length > 0)
            """,
            timeout=timeout_seconds * 1000,
        )
    except PlaywrightTimeoutError:
        print("  Disqus count did not load; Comment Count will be N/A")


def card_metadata(card: Any) -> dict[str, str]:
    title_element = card.locator(".post-tease__title")
    author_element = card.locator(".post-tease__meta-item--author a")
    date_element = card.locator(".tease__meta-item--date")
    comment_element = card.locator(".tease__comment-text")
    link_element = card.locator(".post-tease__h__link")

    href = link_element.get_attribute("href")
    return {
        "title": normalize_text(title_element.inner_text()),
        "author": normalize_text(author_element.inner_text()),
        "time": normalize_text(date_element.inner_text()),
        "comment_count": parse_comment_count(comment_element.inner_text()),
        "url": absolute_url(href, BASE_URL),
    }


def crawl(args: argparse.Namespace) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    with sync_playwright() as playwright:
        browser = launch_browser(playwright, args)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        listing_page = context.new_page()
        article_page = context.new_page()

        try:
            for page_number in range(1, args.pages + 1):
                if args.limit is not None and len(rows) >= args.limit:
                    break

                url = listing_url(page_number)
                print(f"Listing page {page_number}: {url}")
                listing_page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=args.timeout * 1000,
                )
                listing_page.wait_for_selector(
                    "article.tease", timeout=args.timeout * 1000
                )
                wait_for_disqus(listing_page, args.comment_timeout)

                cards = listing_page.locator("article.tease")
                page_items = [card_metadata(cards.nth(i)) for i in range(cards.count())]
                if args.limit is not None:
                    page_items = page_items[: args.limit - len(rows)]

                for item in page_items:
                    print(f"  Article: {item['title']}")
                    article_page.goto(
                        item["url"],
                        wait_until="domcontentloaded",
                        timeout=args.timeout * 1000,
                    )
                    body = article_page.locator(".article__body").first
                    body.wait_for(timeout=args.timeout * 1000)
                    content = clean_article_text(
                        body.evaluate("(element) => element.innerText")
                    )
                    image_values = body.locator("img").evaluate_all(
                        """
                        (images) => images.map((image) =>
                            image.getAttribute('data-src')
                            || image.getAttribute('src')
                            || ''
                        )
                        """
                    )
                    image_urls = unique_urls(
                        absolute_url(value, item["url"]) for value in image_values
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
            context.close()
            browser.close()

    return rows


def main() -> None:
    args = parse_args()
    rows = crawl(args)
    write_csv(rows, args.output)
    print(f"Saved {len(rows)} rows to {args.output.resolve()}")


if __name__ == "__main__":
    main()

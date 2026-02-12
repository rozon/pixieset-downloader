#!/usr/bin/env python3
"""
Pixieset Gallery Downloader

Downloads all images from a Pixieset gallery at maximum resolution.
Supports both public and password-protected galleries.

Usage:
    python downloader.py --url "https://xxx.pixieset.com/gallery/"
    python downloader.py --url "https://xxx.pixieset.com/gallery/" --password "1234"
    python downloader.py --url "https://xxx.pixieset.com/gallery/" --output ./my_photos --concurrent 10
"""

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse, unquote

import aiohttp
from playwright.async_api import async_playwright


PIXIESET_CDN_PATTERN = re.compile(
    r"https?://[^\"'\s]+\.pixi(?:eset)?\.com/[^\"'\s]+\.(?:jpg|jpeg|png|webp|gif)",
    re.IGNORECASE,
)

SIZE_SUFFIXES = ["-small", "-medium", "-large", "-xlarge", "-xxlarge"]
SIZE_SUFFIX_PATTERN = re.compile(
    r"(-(?:small|medium|large|xlarge|xxlarge))\.(jpg|jpeg|png|webp|gif)",
    re.IGNORECASE,
)


def maximize_resolution(url: str) -> tuple[str, str]:
    """Replace any size suffix with -xxlarge to get max resolution.

    Returns (maximized_url, original_url).
    """
    match = SIZE_SUFFIX_PATTERN.search(url)
    if match:
        maximized = SIZE_SUFFIX_PATTERN.sub(r"-xxlarge.\2", url)
        return maximized, url
    # No suffix found — try appending -xxlarge before extension
    ext_match = re.search(r"\.(jpg|jpeg|png|webp|gif)(\?.*)?$", url, re.IGNORECASE)
    if ext_match:
        ext = ext_match.group(1)
        start = ext_match.start()
        maximized = url[:start] + f"-xxlarge.{ext}"
        if ext_match.group(2):
            maximized += ext_match.group(2)
        return maximized, url
    return url, url


def extract_filename(url: str) -> str:
    """Extract a clean filename from a URL."""
    parsed = urlparse(url)
    path = unquote(parsed.path)
    filename = os.path.basename(path)
    # Remove size suffixes from filename for cleanliness
    filename = re.sub(
        r"-(?:small|medium|large|xlarge|xxlarge)\.", ".", filename, flags=re.IGNORECASE
    )
    return filename or "image.jpg"


async def enter_password(page, password: str) -> None:
    """Detect and submit gallery password."""
    print(f"Attempting to enter gallery password...")
    try:
        # Wait for password input to appear
        pwd_input = await page.wait_for_selector(
            'input[type="password"], input[type="text"][name*="password"], '
            'input[placeholder*="password" i], input[placeholder*="contraseña" i], '
            'input.collection-password-input',
            timeout=10_000,
        )
        if pwd_input:
            await pwd_input.fill(password)
            # Look for submit button
            submit_btn = await page.query_selector(
                'button[type="submit"], input[type="submit"], '
                'button:has-text("Submit"), button:has-text("Enter"), '
                'button:has-text("Unlock"), button.collection-password-button'
            )
            if submit_btn:
                await submit_btn.click()
            else:
                await pwd_input.press("Enter")
            # Wait for navigation / gallery load
            await page.wait_for_load_state("networkidle", timeout=15_000)
            print("Password accepted.")
    except Exception as e:
        print(f"Warning: Password entry issue — {e}")
        print("The gallery may be public or the password form was not found.")


async def auto_scroll(page) -> None:
    """Scroll down the page incrementally to trigger lazy loading."""
    print("Scrolling page to load all images...")
    previous_height = 0
    stale_count = 0
    while stale_count < 5:
        current_height = await page.evaluate("document.body.scrollHeight")
        if current_height == previous_height:
            stale_count += 1
        else:
            stale_count = 0
        previous_height = current_height
        await page.evaluate("window.scrollBy(0, window.innerHeight)")
        await asyncio.sleep(0.6)
    # Scroll back to top and wait a moment for any final loads
    await page.evaluate("window.scrollTo(0, 0)")
    await asyncio.sleep(1)


def extract_urls_from_dom_sync(html: str) -> set[str]:
    """Extract image URLs from raw HTML content."""
    urls = set()
    # img src and data-src attributes
    for attr in ["src", "data-src", "data-original", "data-lazy", "data-image"]:
        for match in re.findall(rf'{attr}=["\']([^"\']+)["\']', html, re.IGNORECASE):
            if PIXIESET_CDN_PATTERN.match(match):
                urls.add(match)
    # CSS background-image
    for match in re.findall(r"url\(['\"]?([^)\"']+)['\"]?\)", html, re.IGNORECASE):
        if PIXIESET_CDN_PATTERN.match(match):
            urls.add(match)
    return urls


async def collect_image_urls(page, url: str, password: str | None) -> list[str]:
    """Navigate to gallery and collect all image URLs via network interception + DOM."""
    intercepted_urls: set[str] = set()

    async def on_response(response):
        req_url = response.url
        if PIXIESET_CDN_PATTERN.match(req_url):
            content_type = response.headers.get("content-type", "")
            if "image" in content_type or re.search(
                r"\.(jpg|jpeg|png|webp|gif)", req_url, re.IGNORECASE
            ):
                intercepted_urls.add(req_url)

    page.on("response", on_response)

    # Navigate
    print(f"Navigating to {url} ...")
    await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    try:
        await page.wait_for_load_state("networkidle", timeout=15_000)
    except Exception:
        print("Network did not reach idle state — continuing anyway.")

    # Handle password if needed
    if password:
        await enter_password(page, password)

    # Wait for gallery images to start appearing
    await page.wait_for_timeout(3000)

    # Auto-scroll to trigger lazy loading
    await auto_scroll(page)

    # Extract from DOM as fallback
    html = await page.content()
    dom_urls = extract_urls_from_dom_sync(html)

    all_urls = intercepted_urls | dom_urls

    # Also try to find URLs in any inline scripts / JSON data
    scripts = await page.evaluate("""
        () => {
            const scripts = document.querySelectorAll('script');
            return Array.from(scripts).map(s => s.textContent).join('\\n');
        }
    """)
    for match in PIXIESET_CDN_PATTERN.findall(scripts):
        all_urls.add(match)

    # Filter: keep only actual photo URLs (skip thumbnails/icons that are very small)
    filtered = set()
    for u in all_urls:
        # Skip obvious non-photo assets
        if any(skip in u.lower() for skip in ["/favicon", "/logo", "/icon", "/avatar", "image-protect"]):
            continue
        filtered.add(u)

    print(f"Found {len(filtered)} unique image URL(s).")
    return list(filtered)


async def download_image(
    session: aiohttp.ClientSession,
    url: str,
    output_dir: Path,
    semaphore: asyncio.Semaphore,
    index: int,
    total: int,
    max_retries: int = 3,
) -> bool:
    """Download a single image with retries and resolution maximization."""
    max_url, original_url = maximize_resolution(url)

    async def try_download(download_url: str) -> bool:
        for attempt in range(max_retries):
            try:
                async with semaphore:
                    async with session.get(download_url, timeout=aiohttp.ClientTimeout(total=120)) as resp:
                        if resp.status == 200:
                            filename = extract_filename(download_url)
                            filepath = output_dir / filename
                            # Avoid overwriting — append counter
                            if filepath.exists():
                                stem = filepath.stem
                                suffix = filepath.suffix
                                counter = 1
                                while filepath.exists():
                                    filepath = output_dir / f"{stem}_{counter}{suffix}"
                                    counter += 1
                            data = await resp.read()
                            filepath.write_bytes(data)
                            size_kb = len(data) / 1024
                            print(f"  [{index}/{total}] {filename} ({size_kb:.0f} KB)")
                            return True
                        elif resp.status in (403, 404):
                            return False  # Don't retry on 403/404
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                else:
                    print(f"  [{index}/{total}] Failed after {max_retries} retries: {e}")
        return False

    # Try maximized URL first
    if max_url != original_url:
        if await try_download(max_url):
            return True
        # Fallback to original
        return await try_download(original_url)
    else:
        return await try_download(original_url)


async def download_all(urls: list[str], output_dir: Path, concurrent: int) -> None:
    """Download all images concurrently."""
    output_dir.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(concurrent)
    total = len(urls)
    print(f"\nDownloading {total} image(s) to {output_dir}/ (concurrency: {concurrent})")

    async with aiohttp.ClientSession() as session:
        tasks = [
            download_image(session, url, output_dir, semaphore, i + 1, total)
            for i, url in enumerate(urls)
        ]
        results = await asyncio.gather(*tasks)

    succeeded = sum(1 for r in results if r)
    failed = total - succeeded
    print(f"\nDone: {succeeded} downloaded, {failed} failed out of {total} total.")


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download all images from a Pixieset gallery at maximum resolution."
    )
    parser.add_argument("--url", required=True, help="Pixieset gallery URL")
    parser.add_argument("--password", default=None, help="Gallery password (if protected)")
    parser.add_argument("--output", default="./downloads", help="Output directory (default: ./downloads)")
    parser.add_argument("--concurrent", type=int, default=5, help="Concurrent downloads (default: 5)")
    parser.add_argument("--dry-run", action="store_true", help="List found image URLs without downloading")
    args = parser.parse_args()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        try:
            urls = await collect_image_urls(page, args.url, args.password)
        finally:
            await browser.close()

    if not urls:
        print("No images found. The gallery may be empty, the URL may be wrong, or the password may be incorrect.")
        sys.exit(1)

    if args.dry_run:
        print(f"\n[Dry run] {len(urls)} image(s) found:\n")
        for i, url in enumerate(urls, 1):
            max_url, _ = maximize_resolution(url)
            print(f"  {i}. {max_url}")
        return

    await download_all(urls, Path(args.output), args.concurrent)


if __name__ == "__main__":
    asyncio.run(main())

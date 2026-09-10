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
import getpass
import logging
import os
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

import aiohttp
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright

logger = logging.getLogger("pixieset_downloader")

PIXIESET_CDN_PATTERN = re.compile(
    r"https?://(?:[\w-]+\.)*pixi(?:eset)?\.com/[^\"'\s]+\.(?:jpg|jpeg|png|webp|gif)",
    re.IGNORECASE,
)

SIZE_SUFFIX_NAMES = ("small", "medium", "large", "xlarge", "xxlarge")
SIZE_SUFFIX_ALTERNATION = "|".join(SIZE_SUFFIX_NAMES)
SIZE_SUFFIX_PATTERN = re.compile(
    rf"(-(?:{SIZE_SUFFIX_ALTERNATION}))\.(jpg|jpeg|png|webp|gif)",
    re.IGNORECASE,
)
SIZE_SUFFIX_STRIP_PATTERN = re.compile(rf"-(?:{SIZE_SUFFIX_ALTERNATION})\.", re.IGNORECASE)

COVER_URL_PATTERN = re.compile(
    rf"-cover(?:-(?:{SIZE_SUFFIX_ALTERNATION}))?\.(?:jpg|jpeg|png|webp|gif)(?:\?.*)?$",
    re.IGNORECASE,
)

SKIP_SUBSTRINGS = ("/favicon", "/logo", "/icon", "/avatar", "image-protect")

_UNSAFE_FILENAME_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


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
    filename = SIZE_SUFFIX_STRIP_PATTERN.sub(".", filename)
    return filename or "image.jpg"


def sanitize_basename(name: str) -> str:
    """Strip path components and filesystem-illegal characters from an untrusted name."""
    name = os.path.basename(name)
    name = _UNSAFE_FILENAME_CHARS.sub("_", name).strip()
    return name or "image"


def is_cover_url(url: str) -> bool:
    """True if the URL is Pixieset's cover/hero photo, not a regular gallery photo.

    Cover URLs follow `{hash}-cover.ext` or `{hash}-cover-{size}.ext`; regular
    gallery photos only ever have `{hash}.ext` or `{hash}-{size}.ext` (hashes are
    hex, so this can't collide with a real photo's name).
    """
    return bool(COVER_URL_PATTERN.search(url))


def build_output_filename(
    url: str,
    dom_filename: str | None,
    index: int,
    total: int,
    override_basename: str | None = None,
    is_cover: bool = False,
) -> str:
    """Build the final `NNNN-base.ext` filename for a downloaded image.

    `base` priority: override_basename > dom_filename > URL-derived name.
    The extension is always re-derived from the real image URL, so a
    dom_filename/override that carries a mismatched or missing extension
    never mislabels the actual downloaded file type.

    Cover/hero photos (is_cover=True) are named plainly `cover.ext`, ignoring
    index/override_basename/dom_filename entirely — they aren't part of the
    gallery's numbered sequence.
    """
    url_based = extract_filename(url)
    _, url_ext = os.path.splitext(url_based)
    url_ext = url_ext or ".jpg"

    if is_cover:
        return f"cover{url_ext}"

    width = max(4, len(str(total)))

    if override_basename:
        base = sanitize_basename(override_basename)
    elif dom_filename:
        base = sanitize_basename(dom_filename)
    else:
        base = os.path.splitext(url_based)[0]

    base_stem = os.path.splitext(base)[0] or base
    return f"{index:0{width}d}-{base_stem}{url_ext}"


async def enter_password(page, password: str) -> None:
    """Detect and submit gallery password."""
    logger.info("Attempting to enter gallery password...")
    try:
        # Wait for password input to appear
        pwd_input = await page.wait_for_selector(
            'input[type="password"], input[type="text"][name*="password"], '
            'input[placeholder*="password" i], input[placeholder*="contraseña" i], '
            "input.collection-password-input",
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
            logger.info("Password accepted.")
    except PlaywrightTimeoutError:
        logger.warning("No password form found — the gallery may be public.")
    except PlaywrightError as e:
        logger.warning("Password entry issue: %s", e)


async def auto_scroll(page) -> None:
    """Scroll down the page incrementally to trigger lazy loading."""
    logger.info("Scrolling page to load all images...")
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


def extract_urls_from_dom_sync(html: str) -> list[str]:
    """Extract image URLs from raw HTML content, in first-occurrence order.

    Fallback path only — real ordering/filename pairing comes from
    extract_images_from_dom, which queries the live DOM per-element.
    """
    urls: dict[str, None] = {}
    # img src and data-src attributes
    for attr in ["src", "data-src", "data-original", "data-lazy", "data-image"]:
        for match in re.findall(rf'{attr}=["\']([^"\']+)["\']', html, re.IGNORECASE):
            if PIXIESET_CDN_PATTERN.match(match):
                urls.setdefault(match, None)
    # CSS background-image
    for match in re.findall(r"url\(['\"]?([^)\"']+)['\"]?\)", html, re.IGNORECASE):
        if PIXIESET_CDN_PATTERN.match(match):
            urls.setdefault(match, None)
    return list(urls)


async def extract_images_from_dom(page) -> list[dict]:
    """Query the live DOM in document order for image URLs + optional filename hints.

    Each result: {"url": str, "filename": str | None}, where filename is the
    element's alt attribute (Pixieset embeds the original filename there;
    verified against a live gallery). Order matches document order.
    """
    return await page.evaluate("""
        () => {
            const attrs = ['src', 'data-src', 'data-original', 'data-lazy', 'data-image'];
            const resolve = (val) => {
                try { return new URL(val, location.href).href; } catch (e) { return val; }
            };
            const results = [];
            document.querySelectorAll('img').forEach(img => {
                for (const attr of attrs) {
                    const val = img.getAttribute(attr);
                    if (val) {
                        results.push({ url: resolve(val), filename: img.getAttribute('alt') || null });
                    }
                }
            });
            document.querySelectorAll('[style*="background-image"]').forEach(el => {
                const m = /url\\(['"]?([^)'"]+)['"]?\\)/.exec(el.getAttribute('style') || '');
                if (m) results.push({ url: resolve(m[1]), filename: null });
            });
            return results;
        }
    """)


def is_wanted_image_url(u: str) -> bool:
    """True if a URL looks like an actual gallery photo (matches CDN pattern, not a skip-listed asset)."""
    return bool(PIXIESET_CDN_PATTERN.match(u)) and not any(skip in u.lower() for skip in SKIP_SUBSTRINGS)


def merge_ordered_images(
    dom_images: list[dict],
    extra_urls: list[str],
) -> list[tuple[str, str | None, bool]]:
    """Merge DOM-ordered (url, filename) entries with extra fallback URLs.

    DOM order is preserved and takes precedence; first occurrence wins for dedup,
    but a later duplicate's filename hint can "upgrade" an earlier None. extra_urls
    (network-intercepted / inline-script URLs) are appended only if not already seen,
    with no filename hint. Both inputs are filtered through is_wanted_image_url.
    Each result also carries whether the URL is the gallery's cover/hero photo.
    """
    seen: dict[str, str | None] = {}
    for item in dom_images:
        u = item["url"]
        if not is_wanted_image_url(u):
            continue
        if u not in seen:
            seen[u] = item["filename"]
        elif seen[u] is None and item["filename"]:
            seen[u] = item["filename"]

    for u in extra_urls:
        if is_wanted_image_url(u) and u not in seen:
            seen[u] = None

    return [(u, filename, is_cover_url(u)) for u, filename in seen.items()]


async def collect_image_urls(page, url: str, password: str | None) -> list[tuple[str, str | None, bool]]:
    """Navigate to gallery and collect (url, dom_filename, is_cover) triples in page order.

    DOM element order is the primary source (and the only source that can carry
    a filename hint); network-intercepted and inline-script URLs are merged in
    afterwards as a best-effort fallback for anything the DOM query missed.
    """
    intercepted_urls: set[str] = set()

    async def on_response(response):
        req_url = response.url
        if PIXIESET_CDN_PATTERN.match(req_url):
            content_type = response.headers.get("content-type", "")
            if "image" in content_type or re.search(r"\.(jpg|jpeg|png|webp|gif)", req_url, re.IGNORECASE):
                intercepted_urls.add(req_url)

    page.on("response", on_response)

    # Navigate
    logger.info("Navigating to %s ...", url)
    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
    except PlaywrightTimeoutError:
        logger.error("Timed out loading %s — check the URL and your network connection.", url)
        sys.exit(1)
    except PlaywrightError as e:
        logger.error("Could not load %s: %s", url, e)
        sys.exit(1)
    try:
        await page.wait_for_load_state("networkidle", timeout=15_000)
    except PlaywrightTimeoutError:
        logger.debug("Network did not reach idle state — continuing anyway.")

    # Handle password if needed
    if password:
        await enter_password(page, password)

    # Wait for gallery images to start appearing
    await page.wait_for_timeout(3000)

    # Auto-scroll to trigger lazy loading
    await auto_scroll(page)

    # Extract from live DOM (primary source — preserves page order and filename hints)
    dom_images = await extract_images_from_dom(page)

    # Also try to find URLs in any inline scripts / JSON data (no filename hint available)
    scripts = await page.evaluate("""
        () => {
            const scripts = document.querySelectorAll('script');
            return Array.from(scripts).map(s => s.textContent).join('\\n');
        }
    """)
    script_urls = PIXIESET_CDN_PATTERN.findall(scripts)

    images = merge_ordered_images(dom_images, script_urls + list(intercepted_urls))

    logger.info("Found %d unique image URL(s).", len(images))
    return images


async def download_image(
    session: aiohttp.ClientSession,
    url: str,
    dom_filename: str | None,
    output_dir: Path,
    semaphore: asyncio.Semaphore,
    index: int,
    total: int,
    override_basename: str | None = None,
    is_cover: bool = False,
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
                            filename = build_output_filename(
                                download_url, dom_filename, index, total, override_basename, is_cover
                            )
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
                            logger.info("  [%d/%d] %s (%.0f KB)", index, total, filename, size_kb)
                            return True
                        elif resp.status in (403, 404):
                            return False  # Don't retry on 403/404
            except (TimeoutError, aiohttp.ClientError) as e:
                if attempt < max_retries - 1:
                    await asyncio.sleep(2**attempt)
                else:
                    logger.warning("  [%d/%d] Failed after %d retries: %s", index, total, max_retries, e)
            except OSError as e:
                logger.warning("  [%d/%d] Could not write file: %s", index, total, e)
                return False
        return False

    # Try maximized URL first
    if max_url != original_url:
        if await try_download(max_url):
            return True
        # Fallback to original
        return await try_download(original_url)
    else:
        return await try_download(original_url)


async def download_all(
    images: list[tuple[str, str | None, bool]],
    output_dir: Path,
    concurrent: int,
    override_basename: str | None = None,
) -> None:
    """Download all images concurrently. Cover photos are excluded from the index/total count."""
    output_dir.mkdir(parents=True, exist_ok=True)
    semaphore = asyncio.Semaphore(concurrent)
    total = len(images)
    photo_total = sum(1 for _, _, is_cover in images if not is_cover)
    logger.info("Downloading %d image(s) to %s/ (concurrency: %d)", total, output_dir, concurrent)

    async with aiohttp.ClientSession() as session:
        tasks = []
        photo_idx = 0
        for url, dom_filename, is_cover in images:
            if is_cover:
                idx = 0
            else:
                photo_idx += 1
                idx = photo_idx
            tasks.append(
                download_image(
                    session,
                    url,
                    dom_filename,
                    output_dir,
                    semaphore,
                    idx,
                    photo_total,
                    override_basename,
                    is_cover,
                )
            )
        results = await asyncio.gather(*tasks, return_exceptions=True)

    succeeded = 0
    failed = 0
    for (url, _, _), result in zip(images, results):
        if isinstance(result, Exception):
            logger.warning("Unexpected error downloading %s: %s", url, result)
            failed += 1
        elif result:
            succeeded += 1
        else:
            failed += 1
    logger.info("Done: %d downloaded, %d failed out of %d total.", succeeded, failed, total)


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download all images from a Pixieset gallery at maximum resolution."
    )
    parser.add_argument("--url", required=True, help="Pixieset gallery URL")
    parser.add_argument(
        "--password",
        default=None,
        help=(
            "Gallery password (if protected). Exposed in shell history/process list — prefer --ask-password."
        ),
    )
    parser.add_argument(
        "--ask-password",
        action="store_true",
        help="Prompt for the gallery password securely instead of passing it on the command line",
    )
    parser.add_argument("--output", default="./downloads", help="Output directory (default: ./downloads)")
    parser.add_argument(
        "--filename",
        default=None,
        metavar="BASENAME",
        help=(
            "Use this string as the base filename for every downloaded image "
            "(all images get 'NNNN-BASENAME.ext'; the real image extension is "
            "always preserved). Overrides any filename Pixieset embeds in the page."
        ),
    )
    parser.add_argument("--concurrent", type=int, default=5, help="Concurrent downloads (default: 5)")
    parser.add_argument("--dry-run", action="store_true", help="List found image URLs without downloading")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    parser.add_argument("--quiet", action="store_true", help="Only log warnings and errors")
    args = parser.parse_args()

    log_level = logging.INFO
    if args.verbose:
        log_level = logging.DEBUG
    elif args.quiet:
        log_level = logging.WARNING
    logging.basicConfig(level=log_level, format="%(message)s")

    password = args.password
    if args.ask_password:
        password = getpass.getpass("Gallery password: ")

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
            images = await collect_image_urls(page, args.url, password)
        finally:
            await browser.close()

    if not images:
        logger.error(
            "No images found. The gallery may be empty, the URL may be wrong, "
            "or the password may be incorrect."
        )
        sys.exit(1)

    if args.dry_run:
        logger.info("[Dry run] %d image(s) found:", len(images))
        photo_total = sum(1 for _, _, is_cover in images if not is_cover)
        photo_idx = 0
        for url, dom_filename, is_cover in images:
            max_url, _ = maximize_resolution(url)
            if is_cover:
                idx = 0
            else:
                photo_idx += 1
                idx = photo_idx
            preview_name = build_output_filename(
                max_url, dom_filename, idx, photo_total, args.filename, is_cover
            )
            logger.info("  %s  ->  %s", max_url, preview_name)
        return

    await download_all(images, Path(args.output), args.concurrent, args.filename)


if __name__ == "__main__":
    asyncio.run(main())

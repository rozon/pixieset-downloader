"""Unit tests for downloader.py.

Pure functions (regexes, URL/filename helpers) are tested directly.
download_image/download_all are tested against a fake aiohttp session
so no real network access is required.
"""

import asyncio

import pytest

import downloader as d

# --- maximize_resolution ------------------------------------------------


def test_maximize_resolution_replaces_existing_suffix():
    maximized, original = d.maximize_resolution("https://foo.pixieset.com/a/b-medium.jpg")
    assert maximized == "https://foo.pixieset.com/a/b-xxlarge.jpg"
    assert original == "https://foo.pixieset.com/a/b-medium.jpg"


def test_maximize_resolution_appends_suffix_when_missing():
    maximized, original = d.maximize_resolution("https://foo.pixieset.com/a/b.jpg")
    assert maximized == "https://foo.pixieset.com/a/b-xxlarge.jpg"
    assert original == "https://foo.pixieset.com/a/b.jpg"


def test_maximize_resolution_preserves_query_string():
    maximized, original = d.maximize_resolution("https://foo.pixieset.com/a/b.jpg?token=abc")
    assert maximized == "https://foo.pixieset.com/a/b-xxlarge.jpg?token=abc"
    assert original == "https://foo.pixieset.com/a/b.jpg?token=abc"


def test_maximize_resolution_noop_for_non_image_url():
    maximized, original = d.maximize_resolution("https://foo.pixieset.com/a/b")
    assert maximized == original == "https://foo.pixieset.com/a/b"


# --- extract_filename ----------------------------------------------------


def test_extract_filename_strips_size_suffix():
    assert d.extract_filename("https://foo.pixieset.com/a/b-large.jpg") == "b.jpg"


def test_extract_filename_plain_name():
    assert d.extract_filename("https://foo.pixieset.com/a/photo.jpg") == "photo.jpg"


def test_extract_filename_defaults_when_empty_path():
    assert d.extract_filename("https://foo.pixieset.com/a/") == "image.jpg"


# --- PIXIESET_CDN_PATTERN --------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://cdn1.pixieset.com/foo/bar.jpg",
        "https://foo.pixi.com/bar.jpg",
        "https://pixieset.com/bar.png",
    ],
)
def test_cdn_pattern_matches_pixieset_domains(url):
    assert d.PIXIESET_CDN_PATTERN.match(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://evilpixi.com/bar.jpg",
        "https://mypixiescam.com/bar.jpg",
        "https://notpixieset.example.com/bar.jpg",
    ],
)
def test_cdn_pattern_rejects_lookalike_domains(url):
    assert not d.PIXIESET_CDN_PATTERN.match(url)


# --- extract_urls_from_dom_sync -------------------------------------------


def test_extract_urls_from_dom_sync_collects_known_attributes():
    html = """
    <img src="https://cdn.pixieset.com/a/photo1.jpg">
    <img data-src="https://cdn.pixieset.com/a/photo2.jpg">
    <div style="background-image: url('https://cdn.pixieset.com/a/photo3.jpg')"></div>
    <img src="https://unrelated.example.com/logo.jpg">
    """
    urls = d.extract_urls_from_dom_sync(html)
    assert urls == {
        "https://cdn.pixieset.com/a/photo1.jpg",
        "https://cdn.pixieset.com/a/photo2.jpg",
        "https://cdn.pixieset.com/a/photo3.jpg",
    }


def test_extract_urls_from_dom_sync_empty_html():
    assert d.extract_urls_from_dom_sync("") == set()


# --- download_image / download_all (fake aiohttp session) ----------------


class FakeResponse:
    def __init__(self, status: int, body: bytes = b"", headers: dict | None = None):
        self.status = status
        self._body = body
        self.headers = headers or {}

    async def read(self) -> bytes:
        return self._body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False


class FakeGetContextManager:
    def __init__(self, outcome):
        self._outcome = outcome

    async def __aenter__(self):
        if isinstance(self._outcome, BaseException):
            raise self._outcome
        return self._outcome

    async def __aexit__(self, *exc_info):
        return False


class FakeSession:
    """Stand-in for aiohttp.ClientSession keyed by exact request URL."""

    def __init__(self, outcomes: dict):
        self._outcomes = outcomes
        self.requested_urls: list[str] = []

    def get(self, url, timeout=None):
        self.requested_urls.append(url)
        return FakeGetContextManager(self._outcomes[url])


@pytest.mark.asyncio
async def test_download_image_writes_file_on_success(tmp_path):
    # -xxlarge suffix means maximize_resolution is a no-op, so only one URL is requested.
    url = "https://cdn.pixieset.com/a/photo-xxlarge.jpg"
    session = FakeSession({url: FakeResponse(200, body=b"fake-image-bytes")})
    semaphore = asyncio.Semaphore(1)

    ok = await d.download_image(session, url, tmp_path, semaphore, 1, 1, max_retries=1)

    assert ok is True
    assert (tmp_path / "photo.jpg").read_bytes() == b"fake-image-bytes"


@pytest.mark.asyncio
async def test_download_image_avoids_overwriting_existing_file(tmp_path):
    url = "https://cdn.pixieset.com/a/photo-xxlarge.jpg"
    (tmp_path / "photo.jpg").write_bytes(b"already-here")
    session = FakeSession({url: FakeResponse(200, body=b"new-bytes")})
    semaphore = asyncio.Semaphore(1)

    ok = await d.download_image(session, url, tmp_path, semaphore, 1, 1, max_retries=1)

    assert ok is True
    assert (tmp_path / "photo.jpg").read_bytes() == b"already-here"
    assert (tmp_path / "photo_1.jpg").read_bytes() == b"new-bytes"


@pytest.mark.asyncio
async def test_download_image_returns_false_on_404_without_retry(tmp_path):
    url = "https://cdn.pixieset.com/a/photo-xxlarge.jpg"
    session = FakeSession({url: FakeResponse(404)})
    semaphore = asyncio.Semaphore(1)

    ok = await d.download_image(session, url, tmp_path, semaphore, 1, 1, max_retries=3)

    assert ok is False
    assert session.requested_urls == [url]  # no retries on 404


class RaisingResponse(FakeResponse):
    """Simulates an unexpected error (e.g. disk failure) not caught by download_image."""

    def __init__(self):
        super().__init__(200)

    async def read(self) -> bytes:
        raise RuntimeError("disk exploded")


@pytest.mark.asyncio
async def test_download_all_continues_after_one_unexpected_failure(tmp_path, monkeypatch):
    """Regression test: one task raising should not abort the whole gather() batch."""
    good_url = "https://cdn.pixieset.com/a/good-xxlarge.jpg"
    bad_url = "https://cdn.pixieset.com/a/bad-xxlarge.jpg"

    session = FakeSession(
        {
            good_url: FakeResponse(200, body=b"good-bytes"),
            bad_url: RaisingResponse(),
        }
    )

    class FakeClientSessionFactory:
        async def __aenter__(self):
            return session

        async def __aexit__(self, *exc_info):
            return False

    monkeypatch.setattr(d.aiohttp, "ClientSession", lambda: FakeClientSessionFactory())

    await d.download_all([good_url, bad_url], tmp_path, concurrent=2)

    assert (tmp_path / "good.jpg").read_bytes() == b"good-bytes"
    assert not (tmp_path / "bad.jpg").exists()

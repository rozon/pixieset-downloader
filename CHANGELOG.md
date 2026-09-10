# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.3.0] - 2026-09-09

### Added
- Photos are now numbered by album order and named using metadata embedded in the Pixieset gallery, with a `--filename` option as a fallback/override.
- Cover/hero photo is downloaded separately as `cover.jpg` instead of being numbered with the rest of the album.
- Unit test suite, ruff linting, mypy type-checking, and a CI workflow.

### Fixed
- Hardened downloader robustness (error handling around network/page interaction edge cases).

### Changed
- Bumped project dependencies.

## [0.2.0] - 2026-02-11

### Changed
- Rewrote the downloader from Selenium to Playwright + aiohttp, enabling asynchronous concurrent downloads.
- Switched dependency management to `uv`.

### Added
- `--dry-run` option to preview a download without writing files.

## [0.1.0] - 2023-12-07

### Added
- Initial Selenium-based tool for downloading photos from a Pixieset gallery.

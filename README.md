# Pixieset Downloader

Python script to download all images from a Pixieset gallery at the highest available resolution. Supports both public and password-protected galleries.

## Requirements

- Python 3.14+
- [uv](https://docs.astral.sh/uv/) (package and virtual environment manager)

## Installation

```bash
# 1. Clone or copy the project
cd pixieset-downloader

# 2. Install dependencies (creates the virtual environment automatically)
uv sync

# 3. Install the Chromium browser for Playwright
uv run playwright install chromium
```

## Usage

### Public gallery

```bash
uv run python downloader.py --url "https://example.pixieset.com/my-gallery/"
```

### Password-protected gallery

```bash
uv run python downloader.py --url "https://example.pixieset.com/my-gallery/" --password "1234"
```

### Available options

| Argument          | Required | Default        | Description                              |
|-------------------|----------|----------------|-------------------------------------------|
| `--url`           | Yes      | —              | Pixieset gallery URL                     |
| `--password`      | No       | —              | Gallery password (if protected). Visible in shell history/process list — prefer `--ask-password` |
| `--ask-password`  | No       | —              | Prompt for the password securely instead of passing it on the command line |
| `--output`        | No       | `./downloads`  | Folder where images are saved            |
| `--filename`      | No       | —              | Use this string as the base filename for every photo (`NNNN-BASENAME.ext`); overrides the name Pixieset embeds in the page |
| `--concurrent`    | No       | `5`            | Number of simultaneous downloads         |
| `--dry-run`       | No       | —              | List found image URLs without downloading|
| `--verbose`       | No       | —              | Enable debug logging                     |
| `--quiet`         | No       | —              | Only log warnings and errors             |

### Examples

```bash
# Download to a custom folder
uv run python downloader.py --url "https://example.pixieset.com/wedding/" --output ./wedding-photos

# Download with 10 simultaneous connections
uv run python downloader.py --url "https://example.pixieset.com/wedding/" --concurrent 10

# Preview URLs without downloading
uv run python downloader.py --url "https://example.pixieset.com/wedding/" --dry-run

# Use a custom base filename for every photo (e.g. 0001-wedding-smith.jpg, 0002-wedding-smith.jpg, ...)
uv run python downloader.py --url "https://example.pixieset.com/wedding/" --filename wedding-smith

# All options combined
uv run python downloader.py \
  --url "https://example.pixieset.com/wedding/" \
  --password "secret" \
  --output ./wedding-photos \
  --filename wedding-smith \
  --concurrent 8
```

## How it works

1. **Navigation** — Opens the gallery in a headless Chromium browser using Playwright.
2. **Authentication** — If `--password` is provided, detects the password form and submits it automatically.
3. **Image loading** — Automatically scrolls to the bottom of the page to trigger lazy loading of all images.
4. **URL collection** — Captures image URLs through three methods:
   - Intercepting HTTP responses from the Pixieset CDN in real time.
   - Extracting DOM attributes (`src`, `data-src`, `data-original`, `data-lazy`, `data-image`, `background-image`).
   - Scanning inline scripts and embedded JSON data on the page.
5. **Filename numbering** — Photos are saved in the same order they appear on the gallery page, prefixed with a zero-padded index (`0001-`, `0002-`, ...). The base name comes from the original filename Pixieset embeds in the page when available, falling back to a URL-derived name, or from `--filename` if provided (applied to every photo, still indexed). The gallery's cover/hero photo is excluded from this numbering and saved simply as `cover.jpg`.
6. **Resolution maximization** — Pixieset uses size suffixes in its URLs (`-small`, `-medium`, `-large`, `-xlarge`, `-xxlarge`). The script replaces any suffix with `-xxlarge` to get the highest resolution version. If the server responds with 403/404, it falls back to the original suffix.
7. **Concurrent download** — Downloads images in parallel using `aiohttp` with a semaphore to limit concurrency. Includes automatic retries with exponential backoff.

## Project structure

```
pixieset-downloader/
├── .venv/             # Virtual environment (created by uv)
├── pyproject.toml     # Project definition and dependencies
├── downloader.py      # Main script
└── README.md          # This file
```

## Dependencies

| Package      | Purpose                                               |
|--------------|-------------------------------------------------------|
| `playwright` | Headless browser for rendering JS and scrolling       |
| `aiohttp`    | Concurrent and asynchronous HTTP downloads            |

Both are installed automatically with `uv sync`.

## Troubleshooting

### "No images found"

- Verify the URL is correct and accessible from a regular browser.
- If the gallery requires a password, make sure to pass it with `--password`.
- Some galleries may have non-standard structures; try opening the URL in your browser and verify that images load.

### Timeout or network errors

- Increase concurrency if downloads are too slow: `--concurrent 10`.
- If you get many 403 errors, the server may be rate-limiting requests; reduce concurrency: `--concurrent 2`.

### Playwright cannot find Chromium

Make sure you ran the browser installation step:

```bash
uv run playwright install chromium
```

## Limitations
The downloaded images might still retain watermarks and potentially be of lower quality compared to the originals – which is good to support your local photographers!

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for release history.

## License
This project is licensed under the [MIT License](LICENSE).
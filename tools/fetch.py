#!/usr/bin/env python3
"""
fetch.py — Pull Om Swami ji's blogs and podcast captions into raw/ for processing.

Why this exists
---------------
The Claude Code sandbox blocks direct HTTP fetches of os.me, omswami.org, and
youtube.com. This script runs on your local machine (where network is open) and
deposits text files into ./raw/, which Claude then reads to populate
transcripts.md, distillation.md, and index.md.

Usage
-----
  # one-time install
  brew install yt-dlp
  python3 -m pip install --user requests beautifulsoup4

  # discover sources (lightweight: titles + URLs only)
  python3 tools/fetch.py discover

  # fetch a specific batch of URLs listed in tools/batch.txt
  python3 tools/fetch.py batch

  # fetch a single URL (blog or YouTube) directly
  python3 tools/fetch.py one <url>

  # fetch YouTube channel video list + captions for the oldest N videos
  python3 tools/fetch.py youtube <channel-url> --oldest 10

Output
------
  raw/blogs/<slug>.md            (one per blog post — title, date, body)
  raw/youtube/<channel>/<id>.md  (one per video — title, date, description, captions)
  raw/index.json                 (machine-readable catalogue of everything fetched)

After running, simply tell Claude "process the next 10 from raw/" and the
existing workflow takes over.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse

try:
    import requests
    from bs4 import BeautifulSoup
except ImportError:
    sys.exit("Missing deps. Run: python3 -m pip install --user requests beautifulsoup4")

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "raw"
BLOGS = RAW / "blogs"
YOUTUBE = RAW / "youtube"
INDEX_JSON = RAW / "index.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}

YOUTUBE_CHANNELS = {
    "omswamitv": "https://www.youtube.com/@omswamitv",
    "SriBadrikaAshram": "https://www.youtube.com/@SriBadrikaAshram",
    "Tantratalksofficial": "https://www.youtube.com/@Tantratalksofficial",
}


def slugify(text: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9\-_ ]", "", text).strip().lower()
    return re.sub(r"\s+", "-", text)[:80]


def load_index() -> dict:
    if INDEX_JSON.exists():
        return json.loads(INDEX_JSON.read_text())
    return {"blogs": {}, "youtube": {}}


def save_index(idx: dict) -> None:
    RAW.mkdir(exist_ok=True)
    INDEX_JSON.write_text(json.dumps(idx, indent=2, ensure_ascii=False))


def fetch_blog(url: str) -> Path | None:
    """Fetch a single blog post URL and save as markdown."""
    BLOGS.mkdir(parents=True, exist_ok=True)
    resp = requests.get(url, headers=HEADERS, timeout=30)
    if resp.status_code != 200:
        print(f"  ! {resp.status_code} {url}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    title_el = soup.find("h1") or soup.find("title")
    title = title_el.get_text(strip=True) if title_el else "untitled"

    date = ""
    for sel in ["time", '[itemprop="datePublished"]', ".entry-date", ".published"]:
        el = soup.select_one(sel)
        if el:
            date = el.get("datetime") or el.get_text(strip=True)
            break

    body_el = (
        soup.select_one("article")
        or soup.select_one(".entry-content")
        or soup.select_one(".post-content")
        or soup.select_one("main")
        or soup.body
    )
    body = body_el.get_text("\n", strip=True) if body_el else ""

    slug = slugify(urlparse(url).path.strip("/").split("/")[-1] or title)
    out = BLOGS / f"{slug}.md"
    out.write_text(
        f"# {title}\n\n**Source:** {url}\n**Date:** {date}\n\n---\n\n{body}\n"
    )
    print(f"  ✓ {out.relative_to(ROOT)}")

    idx = load_index()
    idx["blogs"][url] = {"title": title, "date": date, "file": str(out.relative_to(ROOT))}
    save_index(idx)
    return out


def fetch_youtube(channel_url: str, oldest: int = 10) -> None:
    """Fetch channel videos sorted oldest-first via yt-dlp, with captions."""
    if not subprocess.run(["which", "yt-dlp"], capture_output=True).returncode == 0:
        sys.exit("yt-dlp not found. Run: brew install yt-dlp")

    channel_handle = channel_url.rstrip("/").split("/")[-1].lstrip("@")
    out_dir = YOUTUBE / channel_handle
    out_dir.mkdir(parents=True, exist_ok=True)

    # Step 1: list all videos with metadata (no download)
    print(f"Listing videos for {channel_url} …")
    list_proc = subprocess.run(
        [
            "yt-dlp",
            "--flat-playlist",
            "--playlist-reverse",  # oldest first
            "--print", "%(id)s\t%(title)s\t%(upload_date)s",
            f"{channel_url}/videos",
        ],
        capture_output=True, text=True,
    )
    if list_proc.returncode != 0:
        print(list_proc.stderr)
        return

    videos = [line.split("\t") for line in list_proc.stdout.strip().splitlines() if line]
    print(f"  Found {len(videos)} videos. Fetching oldest {oldest} …")

    idx = load_index()
    idx["youtube"].setdefault(channel_handle, {})

    for vid_id, title, date in videos[:oldest]:
        vurl = f"https://www.youtube.com/watch?v={vid_id}"
        if vid_id in idx["youtube"][channel_handle]:
            print(f"  - skip (already have) {vid_id} {title}")
            continue

        # Download auto-captions + description as JSON
        subprocess.run(
            [
                "yt-dlp",
                "--skip-download",
                "--write-auto-subs", "--write-subs",
                "--sub-langs", "en.*,hi.*",
                "--sub-format", "vtt",
                "--write-info-json",
                "-o", str(out_dir / f"{vid_id}.%(ext)s"),
                vurl,
            ],
            capture_output=True,
        )

        # Compose a single markdown file from the artifacts
        info_path = out_dir / f"{vid_id}.info.json"
        info = json.loads(info_path.read_text()) if info_path.exists() else {}
        vtt = next(out_dir.glob(f"{vid_id}*.vtt"), None)
        captions = ""
        if vtt:
            text = vtt.read_text()
            # crude vtt → plain text
            lines = [
                l.strip()
                for l in text.splitlines()
                if l.strip() and "-->" not in l and not l.strip().isdigit()
                and not l.startswith("WEBVTT") and not l.startswith("Kind:")
                and not l.startswith("Language:")
            ]
            captions = "\n".join(lines)

        md = out_dir / f"{vid_id}.md"
        md.write_text(
            f"# {info.get('title', title)}\n\n"
            f"**Channel:** {channel_handle}\n"
            f"**URL:** {vurl}\n"
            f"**Date:** {info.get('upload_date', date)}\n"
            f"**Duration:** {info.get('duration_string', '')}\n\n"
            f"## Description\n\n{info.get('description', '')}\n\n"
            f"## Captions\n\n{captions or '(no captions available)'}\n"
        )
        print(f"  ✓ {md.relative_to(ROOT)}")
        idx["youtube"][channel_handle][vid_id] = {
            "title": info.get("title", title),
            "date": info.get("upload_date", date),
            "file": str(md.relative_to(ROOT)),
            "has_captions": bool(captions),
        }
        save_index(idx)


def discover() -> None:
    """Lightweight: list source listings without bulk-fetching."""
    print("Blogs to explore manually (add post URLs to tools/batch.txt):")
    print("  https://os.me/wisdom")
    print("  https://omswami.org/blog/")
    print()
    print("YouTube channels (use the 'youtube' subcommand):")
    for k, v in YOUTUBE_CHANNELS.items():
        print(f"  {k}: {v}")


def batch() -> None:
    """Fetch every URL listed (one per line) in tools/batch.txt."""
    batch_file = ROOT / "tools" / "batch.txt"
    if not batch_file.exists():
        sys.exit("Create tools/batch.txt with one URL per line.")
    for url in batch_file.read_text().splitlines():
        url = url.strip()
        if not url or url.startswith("#"):
            continue
        print(f"Fetching {url}")
        if "youtube.com" in url or "youtu.be" in url:
            # treat as single-video fetch via youtube subcommand wrapper
            print("  (use: python3 tools/fetch.py youtube <channel-url> for YT)")
            continue
        fetch_blog(url)


def main() -> None:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("discover")
    sub.add_parser("batch")
    p_one = sub.add_parser("one"); p_one.add_argument("url")
    p_yt = sub.add_parser("youtube")
    p_yt.add_argument("channel_url")
    p_yt.add_argument("--oldest", type=int, default=10)

    args = p.parse_args()
    if args.cmd == "discover":
        discover()
    elif args.cmd == "batch":
        batch()
    elif args.cmd == "one":
        fetch_blog(args.url)
    elif args.cmd == "youtube":
        fetch_youtube(args.channel_url, oldest=args.oldest)


if __name__ == "__main__":
    main()

"""Update the badge endpoint with downloads from published installers."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
from urllib.request import Request, urlopen


INSTALLER_RE = re.compile(r"^CrabVault-v\d+\.\d+\.\d+-windows-x64-setup\.exe$")


def count_installer_downloads(releases: list[dict]) -> int:
    total = 0
    for release in releases:
        if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
            continue
        for asset in release.get("assets", []):
            if isinstance(asset, dict) and INSTALLER_RE.fullmatch(str(asset.get("name") or "")):
                total += max(0, int(asset.get("download_count") or 0))
    return total


def fetch_releases(repository: str) -> list[dict]:
    releases: list[dict] = []
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    page = 1
    while True:
        request = Request(
            f"https://api.github.com/repos/{repository}/releases?per_page=100&page={page}",
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "CrabVault-download-badge",
                **({"Authorization": f"Bearer {token}"} if token else {}),
            },
        )
        with urlopen(request, timeout=30) as response:
            batch = json.load(response)
        if not isinstance(batch, list):
            raise ValueError("GitHub API did not return a release list.")
        releases.extend(batch)
        if len(batch) < 100:
            return releases
        page += 1


def write_badge(path: Path, downloads: int) -> None:
    badge = {
        "schemaVersion": 1,
        "label": "downloads",
        "message": str(downloads),
        "color": "bd1531",
    }
    path.write_text(json.dumps(badge, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", default="CrabbedSquare8/CrabVault-Releases")
    parser.add_argument("--output", type=Path, default=Path("download-count.json"))
    args = parser.parse_args()
    write_badge(args.output, count_installer_downloads(fetch_releases(args.repository)))


if __name__ == "__main__":
    main()

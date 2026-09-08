import json
import os
import re
import urllib.request
from pathlib import Path


REPOSITORY = "CrabbedSquare8/CrabVault-Releases"
INSTALLER_NAME = re.compile(
    r"^CrabVault-v\d+\.\d+\.\d+-windows-x64-setup\.exe$",
    re.IGNORECASE,
)
OUTPUT = Path(__file__).resolve().parents[1] / "download-count.json"


def fetch_releases():
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "CrabVault-download-counter",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    releases = []
    page = 1
    while True:
        url = f"https://api.github.com/repos/{REPOSITORY}/releases?per_page=100&page={page}"
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=30) as response:
            batch = json.load(response)
        releases.extend(batch)
        if len(batch) < 100:
            return releases
        page += 1


def main():
    downloads = 0
    for release in fetch_releases():
        if release.get("draft") or release.get("prerelease"):
            continue
        for asset in release.get("assets", []):
            if INSTALLER_NAME.fullmatch(str(asset.get("name", ""))):
                downloads += int(asset.get("download_count", 0))

    payload = {
        "schemaVersion": 1,
        "label": "program downloads",
        "message": str(downloads),
        "color": "bd1531",
    }
    OUTPUT.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

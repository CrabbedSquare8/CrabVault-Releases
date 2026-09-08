import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import app_updates


def make_release(version="0.45.1"):
    name = f"CrabVault-v{version}-windows-x64-setup.exe"
    base = f"https://github.com/{app_updates.REPOSITORY}/releases/download/v{version}/"
    return {"draft": False, "prerelease": False, "tag_name": f"v{version}", "html_url": base, "body": "Correções", "assets": [
        {"name": name, "browser_download_url": base + name, "size": 123},
        {"name": name.removesuffix('.exe') + ".sha256", "browser_download_url": base + name.removesuffix('.exe') + ".sha256"},
    ]}


class AppUpdatesTests(unittest.TestCase):
    def info(self):
        data = make_release()
        return {"release": data, "version": "0.45.1", "installer": data["assets"][0], "checksum": data["assets"][1]}

    def test_semver_is_strict(self):
        self.assertGreater(app_updates._version("v0.44.11"), app_updates._version("0.44.10"))
        with self.assertRaises(ValueError): app_updates._version("0.42")

    def test_release_requires_official_asset_urls(self):
        with patch.object(app_updates, "_read_url", return_value=json.dumps(make_release()).encode()):
            self.assertEqual(app_updates._release()["version"], "0.45.1")
        data = make_release()
        data["assets"][0]["browser_download_url"] = "https://github.com/other/project/releases/download/v1/file.exe"
        with patch.object(app_updates, "_read_url", return_value=json.dumps(data).encode()), self.assertRaisesRegex(RuntimeError, "endereço"):
            app_updates._release()

    def test_check_offers_only_newer_version(self):
        info = self.info()
        with patch.object(app_updates, "_release", return_value=info): self.assertTrue(app_updates.check()["available"])
        info["version"] = "0.43.1"
        with patch.object(app_updates, "_release", return_value=info): self.assertFalse(app_updates.check()["available"])

    def test_verified_installer_is_staged(self):
        payload = b"MZverified installer"
        info = self.info()
        sidecar = f"{hashlib.sha256(payload).hexdigest()}  {info['installer']['name']}\n".encode()
        with tempfile.TemporaryDirectory() as root, patch.object(app_updates, "_release", return_value=info), patch.object(app_updates, "_read_url", side_effect=[sidecar, payload]), patch.object(app_updates.threading.Thread, "start") as start:
            result = app_updates.download_and_install(root, lambda: None)
            self.assertTrue(result["ok"])
            self.assertEqual(Path(result["installer"]).read_bytes(), payload)
            start.assert_called_once()

    def test_modified_installer_is_rejected(self):
        info = self.info()
        sidecar = ("0" * 64 + f"  {info['installer']['name']}\n").encode()
        with tempfile.TemporaryDirectory() as root, patch.object(app_updates, "_release", return_value=info), patch.object(app_updates, "_read_url", side_effect=[sidecar, b"MZmodified"]):
            result = app_updates.download_and_install(root, lambda: None)
            self.assertFalse(result["ok"])
            self.assertIn("SHA-256", result["error"])

    def test_download_stats_count_only_public_stable_installers(self):
        releases = [
            {"draft": False, "prerelease": False, "assets": [
                {"name": "CrabVault-v0.44.11-windows-x64-setup.exe", "download_count": 12},
                {"name": "CrabVault-v0.44.11-windows-x64-setup.sha256", "download_count": 40},
            ]},
            {"draft": False, "prerelease": True, "assets": [
                {"name": "CrabVault-v0.45.0-windows-x64-setup.exe", "download_count": 99},
            ]},
        ]
        with patch.object(app_updates, "_read_url", return_value=json.dumps(releases).encode()), \
             patch.object(app_updates, "_download_stats_cache", None):
            result = app_updates.github_download_stats()
        self.assertTrue(result["ok"])
        self.assertEqual(result["downloads"], 12)
        self.assertEqual(result["release_count"], 1)

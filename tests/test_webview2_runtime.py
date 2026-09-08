from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from backend import webview2_runtime as runtime


class WebView2RuntimeTests(unittest.TestCase):
    def test_detects_highest_valid_runtime(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "Microsoft/EdgeWebView/Application"
            for version in ("119.0.1.0", "152.0.2.3"):
                folder = root / version
                folder.mkdir(parents=True)
                (folder / "msedgewebview2.exe").touch()
            env = {"LOCALAPPDATA": temporary}
            self.assertEqual(runtime.installed_version(env), (152, 0, 2, 3))

    def test_ignores_invalid_or_incomplete_directories(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "Microsoft/EdgeWebView/Application"
            (root / "not-a-version").mkdir(parents=True)
            (root / "152.0.0.0").mkdir()
            self.assertIsNone(runtime.installed_version({"LOCALAPPDATA": temporary}))

    def test_declining_download_stops_before_network(self):
        with patch.object(runtime, "installed_version", return_value=None), \
                patch.object(runtime, "_message", return_value=7), \
                patch.object(runtime, "_download") as download:
            self.assertFalse(runtime.ensure_runtime())
            download.assert_not_called()

    def test_compatible_runtime_needs_no_prompt(self):
        with patch.object(runtime, "installed_version", return_value=(152, 0, 0, 0)), \
                patch.object(runtime, "_message") as message:
            self.assertTrue(runtime.ensure_runtime())
            message.assert_not_called()


if __name__ == "__main__":
    unittest.main()

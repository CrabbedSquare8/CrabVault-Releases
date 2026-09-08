import contextlib
import json
import os
import pathlib
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from backend import portable_check


class PortableCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="manager-portable-check-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(portable_check.storage, "BASE_DIR", str(self.root)))
        self.stack.enter_context(patch.object(portable_check.storage, "RESOURCE_DIR", str(self.root)))
        self.stack.enter_context(patch.object(pathlib.Path, "is_file", return_value=True))
        config = {"runtimeOptions": {"includedFrameworks": [{"name": "Microsoft.NETCore.App", "version": "10.0.11"}]}}
        self.config = self.stack.enter_context(patch.object(pathlib.Path, "read_text", return_value=json.dumps(config)))
        self.run = self.stack.enter_context(patch.object(portable_check.subprocess, "run", side_effect=[
            subprocess.CompletedProcess([], 1, '{"ok":false,"error":"--archives ausente"}', ""),
            subprocess.CompletedProcess([], 0, "Usage: UAssetTool <command>\n list_iostore", ""),
        ]))

    def test_each_reader_uses_its_own_runtime_without_changing_parent_environment(self):
        original = {"PATH": "external tools", "DOTNET_ROOT": "external runtime", "DOTNET_ROOT_X64": "external runtime"}
        with patch.dict(os.environ, original):
            report = portable_check.check_distribution()
            self.assertEqual({key: os.environ[key] for key in original}, original)
        self.assertTrue(report["ok"], report)
        self.assertTrue(report["native_bootstrap"])
        self.assertTrue(report["uassettool_bootstrap"])
        first, second = self.run.call_args_list
        self.assertEqual(first.kwargs["env"]["PATH"], "")
        self.assertNotEqual(first.kwargs["env"]["DOTNET_ROOT_X64"], "external runtime")
        self.assertEqual(second.kwargs["env"]["PATH"], "")
        self.assertEqual(second.kwargs["env"]["DOTNET_ROOT_X64"], str(self.root / "tools/dotnet8"))
        self.assertEqual(second.args[0][-1], "--help")

    def test_asset_reader_runtime_failure_cannot_report_package_as_ready(self):
        self.run.side_effect = [
            subprocess.CompletedProcess([], 1, '{"ok":false,"error":"--archives ausente"}', ""),
            subprocess.CompletedProcess([], 2147516547, "", "You must install .NET"),
        ]
        report = portable_check.check_distribution()
        self.assertFalse(report["ok"])
        self.assertTrue(report["native_bootstrap"])
        self.assertFalse(report["uassettool_bootstrap"])
        self.assertIn(".NET 8", report["error"])

    def test_framework_dependent_extractor_is_rejected_before_launch(self):
        self.config.return_value = json.dumps({"runtimeOptions": {"framework": {"name": "Microsoft.NETCore.App", "version": "10.0.0"}}})
        report = portable_check.check_distribution()
        self.assertFalse(report["ok"])
        self.assertIn(".NET externo", report["error"])
        self.run.assert_not_called()

    def test_malformed_runtime_metadata_returns_diagnostic_instead_of_crashing(self):
        self.config.return_value = json.dumps({"runtimeOptions": []})
        self.assertFalse(portable_check.check_distribution()["ok"])
        self.run.assert_not_called()


if __name__ == "__main__":
    unittest.main()

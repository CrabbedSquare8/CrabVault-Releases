import contextlib
import copy
import json
import pathlib
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from backend import mod_ops, native3d_jobs


class NativePreviewTests(unittest.TestCase):
    def setUp(self):
        work = pathlib.Path(mod_ops._NATIVE3D_WORK_ROOT)
        work.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="unit-", dir=work)
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.files = []
        for name in ("fixture.pak", "fixture.utoc", "fixture.ucas", "mapping.usmap", "oodle.dll",
                     "zlib.dll", "extractor.exe", "global.utoc", "global.ucas"):
            path = self.root / name
            path.write_bytes(b"fixture")
            self.files.append(path)
        self.mod = {"id": "m1", "components": [{"id": "c1", "name": "fixture", "types": ["Mesh"]}]}
        self.saved = self.stack.enter_context(patch.object(mod_ops.storage, "save_mods"))
        self.stack.enter_context(patch.object(mod_ops.storage, "load_mods", return_value=[self.mod]))
        self.stack.enter_context(patch.object(mod_ops.storage, "load_settings", return_value={}))
        self.stack.enter_context(patch.object(mod_ops, "_record_activity"))
        self.stack.enter_context(patch.object(mod_ops, "_mod_source_files", return_value=[]))
        self.stack.enter_context(patch.object(mod_ops, "_component_source_files", return_value=list(map(str, self.files[:3]))))
        self.stack.enter_context(patch.object(mod_ops, "_native3d_support_files", return_value=tuple(self.files[3:6])))
        self.stack.enter_context(patch.object(mod_ops, "_native3d_game_global_files", return_value=tuple(self.files[7:])))
        self.stack.enter_context(patch.object(mod_ops, "_native3d_extractor_command", return_value=[str(self.files[6])]))
        self.stack.enter_context(patch.object(mod_ops, "_NATIVE3D_EXTRACTOR_EXE", str(self.files[6])))
        self.stack.enter_context(patch.object(mod_ops, "_NATIVE3D_CACHE_ROOT", str(self.root / "cache")))
        self.stack.enter_context(patch.object(mod_ops, "_NATIVE3D_WORK_ROOT", str(self.root / "work")))
        self.stack.enter_context(patch.object(mod_ops, "_cached_bundle_paths", side_effect=AssertionError("Preview must not scan via UAssetTool")))
        self.calls = []
        self.archive_lists = []
        self.stack.enter_context(patch.object(native3d_jobs.PreviewJob, "run", lambda job, cmd: self.fake_run(cmd)))

    def fake_run(self, command):
        self.calls.append(command)
        stage = pathlib.Path(command[command.index("--archives") + 1])
        self.archive_lists.append({
            "components": pathlib.Path(command[command.index("--component-containers") + 1]).read_text(encoding="utf-8").splitlines(),
            "globals": pathlib.Path(command[command.index("--global-containers") + 1]).read_text(encoding="utf-8").splitlines(),
            "staged_files": {path.name for path in stage.iterdir()},
            "stage": stage,
        })
        out = pathlib.Path(command[command.index("--output") + 1])
        key = command[command.index("--model") + 1] if "--model" in command else "body"
        path = out / f"{key}.glb"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"materials": [{"name": "Body"}]}).encode()
        payload += b" " * (-len(payload) % 4)
        path.write_bytes(struct.pack("<4sIIII", b"glTF", 2, 20 + len(payload), len(payload), 0x4E4F534A) + payload)
        (out / "T_Body_D.png").write_bytes(b"fixture texture")
        response = {"ok": True, "selected": key, "meshes": [str(path)],
                    "models": [{"key": "body", "name": "Body"}, {"key": "lobby", "name": "Lobby"}]}
        return subprocess.CompletedProcess(command, 0, json.dumps(response), "")

    def test_first_open_prepares_only_default_and_never_writes_catalog(self):
        before = copy.deepcopy(self.mod)
        result = mod_ops.prepare_component_3d_preview("m1", "c1")
        self.assertTrue(result["ok"], result)
        self.assertEqual([item["ready"] for item in result["models"]], [True, False])
        self.assertEqual(len(self.calls), 1)
        self.saved.assert_not_called()
        self.assertEqual(self.mod, before)

    def test_containers_are_read_in_place_even_when_game_files_are_large(self):
        original_size = mod_ops.os.path.getsize
        global_paths = {str(path) for path in self.files[7:]}

        def file_size(path):
            return 2 * 1024 ** 3 if str(path) in global_paths else original_size(path)

        with patch.object(mod_ops.os, "link", side_effect=AssertionError("No game hardlinks")), \
                patch.object(mod_ops.shutil, "copy2", side_effect=AssertionError("No game copies")), \
                patch.object(mod_ops.os.path, "getsize", side_effect=file_size):
            result = mod_ops.prepare_component_3d_preview("m1", "c1")
        self.assertTrue(result["ok"], result)
        archives = self.archive_lists[0]
        self.assertEqual(archives["components"], list(map(str, self.files[:3])))
        self.assertEqual(archives["globals"], list(map(str, self.files[7:])))
        self.assertTrue(all(pathlib.Path(path).is_absolute()
                            for path in archives["components"] + archives["globals"]))
        self.assertEqual(archives["staged_files"], {"component-containers.txt", "global-containers.txt"})
        self.assertFalse(archives["stage"].exists())
        self.assertTrue(all(path.read_bytes() == b"fixture" for path in self.files))
        self.saved.assert_not_called()

    def test_lazy_variant_merges_cache_and_keeps_shared_textures(self):
        first = mod_ops.prepare_component_3d_preview("m1", "c1")
        texture = self.root / "cache/m1/c1/model/T_Body_D.png"
        old_bytes = texture.read_bytes()
        second = mod_ops.prepare_component_3d_preview("m1", "c1", "lobby")
        self.assertTrue(all(item["ready"] for item in second["models"]))
        self.assertEqual(second["selected"], "lobby")
        self.assertEqual(first["models"][0]["url"], second["models"][0]["url"])
        self.assertEqual(texture.read_bytes(), old_bytes)
        again = mod_ops.prepare_component_3d_preview("m1", "c1")
        self.assertTrue(again["cached"])
        self.assertEqual(again["selected"], "body")
        self.assertEqual(len(self.calls), 2)

    def test_cached_preview_does_not_wait_for_another_conversion(self):
        mod_ops.prepare_component_3d_preview("m1", "c1")
        result = []
        thread = threading.Thread(target=lambda: result.append(mod_ops.prepare_component_3d_preview("m1", "c1")))
        with mod_ops._NATIVE3D_PREVIEW_LOCK:
            thread.start()
            thread.join(2)
            done = not thread.is_alive()
        thread.join(2)
        self.assertTrue(done, "A cache hit was blocked by another preview")
        self.assertTrue(result[0]["cached"])

    def test_missing_texture_is_rebuilt(self):
        mod_ops.prepare_component_3d_preview("m1", "c1")
        (self.root / "cache/m1/c1/model/T_Body_D.png").unlink()
        result = mod_ops.prepare_component_3d_preview("m1", "c1")
        self.assertTrue(result["ok"])
        self.assertFalse(result["cached"])
        self.assertEqual(len(self.calls), 2)

    def test_component_or_gpu_change_invalidates_cache(self):
        mod_ops.prepare_component_3d_preview("m1", "c1")
        self.files[0].write_bytes(b"updated fixture")
        self.assertFalse(mod_ops.prepare_component_3d_preview("m1", "c1")["cached"])
        result = mod_ops.prepare_component_3d_preview("m1", "c1", gpu_formats=["bc7", "invalid", None])
        self.assertFalse(result["cached"])
        self.assertEqual(self.calls[-1][-1], "bc7")
        self.assertEqual(len(self.calls), 3)

    def test_unknown_variant_never_runs_native_again(self):
        mod_ops.prepare_component_3d_preview("m1", "c1")
        result = mod_ops.prepare_component_3d_preview("m1", "c1", "not-in-this-component")
        self.assertFalse(result["ok"])
        self.assertEqual(len(self.calls), 1)

    def test_failed_extractor_cannot_publish_partial_geometry(self):
        def failure(job, command):
            self.fake_run(command)
            return subprocess.CompletedProcess(command, 1, '{"ok":false,"error":"fixture failure"}', "")
        with patch.object(native3d_jobs.PreviewJob, "run", failure):
            result = mod_ops.prepare_component_3d_preview("m1", "c1")
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "fixture failure")
        result = mod_ops.prepare_component_3d_preview("m1", "c1")
        self.assertTrue(result["ok"])
        self.assertEqual(len(self.calls), 2)

    def test_cancel_before_start_leaves_no_cache_or_native_process(self):
        native3d_jobs.cancel("unit-early-cancel")
        result = mod_ops.prepare_component_3d_preview("m1", "c1", request_id="unit-early-cancel")
        self.assertTrue(result["cancelled"])
        self.assertEqual(self.calls, [])
        self.assertFalse((self.root / "cache").exists())

    def test_cache_rejects_a_model_path_outside_its_component(self):
        mod_ops.prepare_component_3d_preview("m1", "c1")
        path = self.root / "cache/m1/c1/manifest.json"
        manifest = json.loads(path.read_text())
        manifest["result"]["models"][0]["url"] = mod_ops._native3d_frontend_url(str(self.files[0]))
        path.write_text(json.dumps(manifest), encoding="utf-8")
        result = mod_ops.prepare_component_3d_preview("m1", "c1")
        self.assertTrue(result["ok"])
        self.assertFalse(result["cached"])
        self.assertEqual(len(self.calls), 2)


class NativeExtractorCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="native3d-command-")
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        self.exe = self.root / "Marvel3DExtractor.exe"
        self.dotnet = self.root / "sdk" / "dotnet.exe"
        self.dll = self.root / "development" / "Marvel3DExtractor.dll"
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        for name, path in (("_NATIVE3D_EXTRACTOR_EXE", self.exe),
                           ("_NATIVE3D_DOTNET", self.dotnet),
                           ("_NATIVE3D_EXTRACTOR_DLL", self.dll)):
            self.stack.enter_context(patch.object(mod_ops, name, str(path)))

    def create(self, *paths):
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fixture")

    def test_bundled_executable_takes_precedence_over_development_sdk(self):
        self.create(self.exe, self.dotnet, self.dll)
        self.assertEqual(mod_ops._native3d_extractor_command(), [str(self.exe)])

    def test_bundled_executable_requires_no_development_sdk(self):
        self.create(self.exe)
        self.assertEqual(mod_ops._native3d_extractor_command(), [str(self.exe)])

    def test_development_fallback_requires_both_sdk_and_assembly(self):
        self.create(self.dotnet)
        with self.assertRaises(OSError):
            mod_ops._native3d_extractor_command()
        self.create(self.dll)
        self.assertEqual(mod_ops._native3d_extractor_command(), [str(self.dotnet), str(self.dll)])
        self.dotnet.unlink()
        with self.assertRaises(OSError):
            mod_ops._native3d_extractor_command()

    def test_missing_distribution_returns_actionable_error(self):
        with self.assertRaisesRegex(OSError, "extrator 3D"):
            mod_ops._native3d_extractor_command()


class NativeJobTests(unittest.TestCase):
    def test_cancel_terminates_only_its_own_child_and_releases_request(self):
        caught = []
        with native3d_jobs.request("unit-process-cancel") as job:
            def run():
                try:
                    job.run([sys.executable, "-B", "-c", "import time; time.sleep(30)"])
                except native3d_jobs.PreviewCancelled:
                    caught.append(True)
            thread = threading.Thread(target=run)
            thread.start()
            deadline = time.monotonic() + 3
            while job._process is None and time.monotonic() < deadline:
                time.sleep(0.01)
            child = job._process
            native3d_jobs.cancel("unit-process-cancel")
            thread.join(3)
            self.assertFalse(thread.is_alive())
            self.assertEqual(caught, [True])
            self.assertIsNotNone(child)
            self.assertIsNotNone(child.poll())
        self.assertNotIn("unit-process-cancel", native3d_jobs._jobs)


if __name__ == "__main__":
    unittest.main()

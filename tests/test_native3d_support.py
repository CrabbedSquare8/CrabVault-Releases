import copy
import gzip
import hashlib
import io
import json
import pathlib
import struct
import tempfile
import threading
import unittest
import urllib.parse
import zipfile
from unittest.mock import patch

from backend import native3d_support as support
from backend.operation_jobs import OperationCancelled

REAL_DOWNLOAD = support._download


def mapping_bytes(payload=b"mapping body"):
    return b"\xc4\x30\x04" + struct.pack("<IBII", 0, 0, len(payload), len(payload)) + payload


def dll_bytes():
    data = bytearray(512)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 0x3c, 128)
    data[128:132] = b"PE\0\0"
    struct.pack_into("<H", data, 132, 0x8664)
    struct.pack_into("<H", data, 150, 0x2000)
    return bytes(data)


def entry(build, data):
    name = f"5.3.2-{build}+++depot_marvel+S9.5_release-Marvel.usmap"
    return {"type": "file", "name": name, "size": len(data),
            "sha": hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()}


class NativeSupportTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="manager-support-test-")
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name) / "support"
        self.addCleanup(patch.stopall)
        patch.object(support, "SUPPORT_DIR", self.root).start()
        self.mapping = mapping_bytes()
        self.entries = [entry(100, self.mapping), entry(200, self.mapping)]
        dll = dll_bytes()
        self.specs = copy.deepcopy(support.CODECS)
        self.archives = {}
        for kind, spec in self.specs.items():
            if spec["format"] == "raw":
                data = dll
            elif spec["format"] == "zip":
                stream = io.BytesIO()
                with zipfile.ZipFile(stream, "w") as archive:
                    archive.writestr(spec["entry"], dll)
                    archive.writestr("../../escape.exe", b"never extract unrelated entries")
                data = stream.getvalue()
            else:
                data = gzip.compress(dll)
            self.archives[spec["url"]] = data
            spec["sha256"] = hashlib.sha256(dll).hexdigest()
            spec["archive_sha256"] = hashlib.sha256(data).hexdigest()
        patch.object(support, "CODECS", self.specs).start()
        self.fetch = patch.object(support, "_download", side_effect=self.download).start()

    def download(self, url, limit, check=None):
        support._check(check)
        if url == support.MAPPING_INDEX:
            return json.dumps(self.entries).encode()
        if url.startswith(support.MAPPING_BASE):
            return self.mapping
        return self.archives[url]

    def test_fresh_install_needs_no_external_settings_and_is_reusable_offline(self):
        self.assertFalse(support.get_status()["ready"])
        self.fetch.assert_not_called()
        paths = support.ensure_support({"fmodel_path": "Z:/missing/FModel.exe"})
        self.assertEqual(len(paths), 3)
        self.assertTrue(all(path.is_file() and path.is_relative_to(self.root) for path in paths))
        status = support.get_status()
        self.assertTrue(status["ready"], status)
        self.assertEqual(status["mapping_build"], 200)
        self.assertTrue(any(call.args[0] == self.specs["oodle"]["url"]
                            for call in self.fetch.call_args_list))
        self.fetch.reset_mock()
        self.fetch.side_effect = AssertionError("network must not be used offline")
        self.assertEqual(support.ensure_support(), paths)
        self.assertTrue(support.get_status()["ready"])
        self.fetch.assert_not_called()
        self.assertFalse((self.root.parent / "escape.exe").exists())

    def test_latest_release_ignores_preview_wrong_game_and_remote_urls(self):
        bad = entry(999, self.mapping)
        bad["name"] = "PY_" + bad["name"]
        wrong = entry(9999, self.mapping)
        wrong["name"] = wrong["name"].replace("-Marvel.usmap", "-Other.usmap")
        traversal = entry(8888, self.mapping)
        traversal["name"] = "../../" + traversal["name"]
        self.entries += [bad, wrong, traversal]
        self.entries[1]["download_url"] = "https://attacker.invalid/payload.exe"
        support.ensure_support()
        self.assertEqual(support.get_status()["mapping_build"], 200)
        self.assertTrue(all("attacker" not in call.args[0] for call in self.fetch.call_args_list))

    def test_explicit_update_swaps_only_mapping_and_preserves_previous_files(self):
        previous = support.ensure_support()
        self.mapping = mapping_bytes(b"new body")
        self.entries = [entry(300, self.mapping)]
        self.fetch.reset_mock()
        updated = support.ensure_support(update=True)
        self.assertNotEqual(previous[0], updated[0])
        self.assertEqual(previous[1:], updated[1:])
        self.assertTrue(previous[0].is_file())
        self.assertEqual(support.get_status()["mapping_build"], 300)
        self.assertEqual(self.fetch.call_count, 2)

    def test_unchanged_update_preserves_mtime_used_by_model_cache(self):
        paths = support.ensure_support()
        old = [path.stat().st_mtime_ns for path in paths]
        support.ensure_support(update=True)
        self.assertEqual([path.stat().st_mtime_ns for path in paths], old)

    def test_failed_update_keeps_valid_snapshot_available(self):
        paths = support.ensure_support()
        before = (self.root / "current.json").read_bytes()
        self.fetch.side_effect = support.SupportError("Sem conexão.")
        with self.assertRaisesRegex(support.SupportError, "continua disponível"):
            support.ensure_support(update=True)
        self.assertEqual((self.root / "current.json").read_bytes(), before)
        self.assertEqual(support.ensure_support(), paths)
        self.assertTrue(support.get_status()["ready"])

    def test_downgrade_is_rejected(self):
        support.ensure_support()
        before = (self.root / "current.json").read_bytes()
        self.entries = [entry(10, self.mapping)]
        with self.assertRaisesRegex(support.SupportError, "mais antigo"):
            support.ensure_support(update=True)
        self.assertEqual((self.root / "current.json").read_bytes(), before)

    def test_corrupt_cached_dll_repaired_before_return(self):
        paths = support.ensure_support()
        paths[1].write_bytes(b"MZ broken")
        self.assertFalse(support.get_status()["ready"])
        paths = support.ensure_support()
        self.assertEqual(paths[1].read_bytes(), dll_bytes())
        self.assertTrue(support.get_status()["ready"])

    def test_untrusted_manifest_cannot_supply_dll_digest(self):
        support.ensure_support()
        manifest_path = self.root / "current.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["oodle"]["sha256"] = "a" * 64
        manifest_path.write_text(json.dumps(manifest))
        self.assertFalse(support.get_status()["ready"])

    def test_hash_mismatch_and_non_usmap_never_publish(self):
        self.mapping = b"<html>bad upstream reply</html>"
        with self.assertRaisesRegex(support.SupportError, "não corresponde"):
            support.ensure_support()
        self.assertFalse((self.root / "current.json").exists())
        self.entries = [entry(200, self.mapping)]
        with self.assertRaisesRegex(support.SupportError, "USMAP"):
            support.ensure_support()
        self.assertFalse((self.root / "current.json").exists())

    def test_codec_archive_hash_mismatch_never_publishes(self):
        self.archives[self.specs["zlib"]["url"]] = b"broken gzip"
        with self.assertRaisesRegex(support.SupportError, "versão verificada"):
            support.ensure_support()
        self.assertFalse((self.root / "current.json").exists())

    def test_oodle_download_hash_mismatch_never_publishes(self):
        self.archives[self.specs["oodle"]["url"]] = dll_bytes() + b"changed"
        with self.assertRaisesRegex(support.SupportError, "versão verificada"):
            support.ensure_support()
        self.assertFalse((self.root / "current.json").exists())

    def test_legacy_oodle_cache_is_replaced_from_pinned_download(self):
        paths = support.ensure_support()
        manifest_path = self.root / "current.json"
        manifest = json.loads(manifest_path.read_text())
        legacy_data = dll_bytes() + b"legacy"
        legacy_digest = hashlib.sha256(legacy_data).hexdigest()
        legacy_path = support._record_path("oodle", legacy_digest)
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_path.write_bytes(legacy_data)
        manifest["oodle"] = {"version": "2.9.16", "sha256": legacy_digest, "source": "legacy"}
        manifest_path.write_text(json.dumps(manifest))
        paths[1].unlink()
        with patch.object(support, "LEGACY_CODEC_DIGESTS", {"oodle": {legacy_digest}}):
            self.fetch.reset_mock()
            migrated = support.ensure_support()
        self.assertEqual(migrated[0], paths[0])
        self.assertEqual(migrated[2], paths[2])
        self.assertEqual(migrated[1].read_bytes(), dll_bytes())
        self.assertTrue(any(call.args[0] == self.specs["oodle"]["url"]
                            for call in self.fetch.call_args_list))

    def test_cancellation_does_not_publish_a_partial_snapshot(self):
        original = support._ensure_codec
        cancelled = threading.Event()

        def codecs(kind, check):
            result = original(kind, check)
            cancelled.set()
            return result

        def check():
            if cancelled.is_set():
                raise OperationCancelled()

        with patch.object(support, "_ensure_codec", side_effect=codecs):
            with self.assertRaises(OperationCancelled):
                support.ensure_support(check=check)
        self.assertFalse((self.root / "current.json").exists())
        self.assertFalse(list(self.root.rglob(".download-*")))

    def test_waiting_for_another_thread_remains_cancellable(self):
        entered = threading.Event()
        release = threading.Event()

        def other():
            with support._LOCK:
                entered.set()
                release.wait(2)

        thread = threading.Thread(target=other)
        thread.start()
        self.assertTrue(entered.wait(1))
        checks = []

        def check():
            checks.append(True)
            if len(checks) >= 2:
                raise OperationCancelled()

        try:
            with self.assertRaises(OperationCancelled):
                support.ensure_support(check=check)
        finally:
            release.set()
            thread.join(2)
        self.fetch.assert_not_called()

    def test_interrupted_publication_keeps_previous_manifest(self):
        support.ensure_support()
        previous = (self.root / "current.json").read_bytes()
        self.mapping = mapping_bytes(b"replacement")
        self.entries = [entry(300, self.mapping)]
        with patch.object(support.storage, "_save_json", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                support.ensure_support(update=True)
        self.assertEqual((self.root / "current.json").read_bytes(), previous)
        self.assertTrue(support.get_status()["ready"])

    def test_oversized_stream_and_mapping_allocations_are_rejected(self):
        with self.assertRaises(support.SupportError):
            support._read_limited(io.BytesIO(b"123456"), 5)
        data = bytearray(mapping_bytes())
        struct.pack_into("<I", data, 12, 1024 * 1024 * 1024)
        with self.assertRaises(support.SupportError):
            support._validate_mapping(data)

    def test_non_dll_and_wrong_architecture_are_rejected(self):
        data = bytearray(dll_bytes())
        struct.pack_into("<H", data, 132, 0x014c)
        with self.assertRaises(support.SupportError):
            support._validate_dll(data)
        data = bytearray(dll_bytes())
        struct.pack_into("<H", data, 150, 0)
        with self.assertRaises(support.SupportError):
            support._validate_dll(data)

    def test_suspicious_urls_rejected_including_redirects(self):
        support._validate_url(support.MAPPING_INDEX)
        support._validate_url(self.specs["zlib"]["url"])
        support._validate_url("https://release-assets.githubusercontent.com/asset?signature=x", True)
        for url in ("http://api.github.com/repos/SpaceDepot/rivals-depot/contents/usmap?ref=main",
                    "https://github.com.attacker.invalid/payload", "https://localhost/payload",
                    "file:///C:/Windows/System32/evil.dll", "https://user:secret@github.com/file",
                    "https://github.com:badport/file",
                    "https://github.com/another/repo/releases/file.dll",
                    "https://release-assets.githubusercontent.com/asset"):
            with self.subTest(url=url), self.assertRaises(support.SupportError):
                support._validate_url(url)

    def test_download_rejects_truncation_and_oversized_content_length(self):
        for length, content in (("6", b"123"), ("200", b"1"), ("invalid", b"1")):
            with self.subTest(length=length):
                response = io.BytesIO(content)
                response.headers = {"Content-Length": length}
                response.geturl = lambda: support.MAPPING_INDEX
                with patch.object(support.urllib.request.OpenerDirector, "open", return_value=response):
                    with self.assertRaises(support.SupportError):
                        REAL_DOWNLOAD(support.MAPPING_INDEX, 10)

    def test_download_does_not_follow_redirect_to_untrusted_host(self):
        redirect = support._RestrictedRedirect(True)
        with self.assertRaises(support.SupportError):
            redirect.redirect_request(None, None, 302, "Found", {}, "https://attacker.invalid/payload")

    def test_slow_download_is_bounded_by_wall_time(self):
        with patch.object(support.time, "monotonic", return_value=100), self.assertRaisesRegex(support.SupportError, "demorou"):
            support._read_limited(io.BytesIO(b"payload"), 20, deadline=90)

    def test_atomic_cache_files_do_not_activate_new_manifest_on_failure(self):
        with patch.object(support.os, "replace", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                support.ensure_support()
        self.assertFalse((self.root / "current.json").exists())
        self.assertFalse(list(self.root.rglob(".download-*")))


if __name__ == "__main__":
    unittest.main()

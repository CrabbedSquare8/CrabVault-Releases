import os
import pathlib
import tempfile
import unittest
import zipfile
from unittest.mock import Mock, patch

import main
from backend import storage


class ArchiveImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        paths = patch.multiple(storage, MODS_JSON=str(self.root / "mods.json"),
                               SETTINGS_FILE=str(self.root / "settings.json"),
                               STORAGE_DIR=str(self.root / "library"), BACKUPS_DIR=str(self.root / "backups"))
        paths.start()
        self.addCleanup(paths.stop)
        analysis = patch.object(main.mod_ops, "_paths_from_bundle", return_value=[])
        analysis.start()
        self.addCleanup(analysis.stop)
        storage.ensure_dirs()
        self.destination = self.root / "extracted"
        self.destination.mkdir()
        main.pending_imports.clear()
        self.addCleanup(main.pending_imports.clear)

    def test_zip_still_extracts_natively(self):
        archive = self.root / "mod.ZIP"
        with zipfile.ZipFile(archive, "w") as z:
            z.writestr("variant/mod.pak", b"pak")
        with patch.object(main.tempfile, "mkdtemp", return_value=str(self.destination)), patch.object(
                main.subprocess, "run", side_effect=AssertionError("ZIP is native")):
            output = main._extract_archive(str(archive))
        self.assertEqual((pathlib.Path(output) / "variant/mod.pak").read_bytes(), b"pak")

    def test_loose_packages_are_archived_together_without_name_collisions(self):
        first = self.root / "first"
        second = self.root / "second"
        first.mkdir()
        second.mkdir()
        sources = []
        for folder in (first, second):
            for extension in (".pak", ".utoc", ".ucas"):
                path = folder / ("Shared" + extension)
                path.write_bytes((folder.name + extension).encode())
                sources.append(str(path))
        output = self.root / "selected.zip"

        main._create_loose_package_archive(sources, str(output))

        with zipfile.ZipFile(output) as archive:
            names = archive.namelist()
            self.assertEqual(len(names), 6)
            self.assertTrue(all(name.startswith(("Pacote 01 - Shared/", "Pacote 02 - Shared/")) for name in names))
            self.assertEqual(archive.read("Pacote 01 - Shared/Shared.pak"), b"first.pak")
            self.assertEqual(archive.read("Pacote 02 - Shared/Shared.pak"), b"second.pak")

    def test_winrar_extracts_7z_without_interactive_prompts(self):
        with patch.object(main.tempfile, "mkdtemp", return_value=str(self.destination)), patch.object(
                main, "_find_archive_extractor", return_value=("winrar", "WinRAR.exe")), patch.object(
                main.subprocess, "run", return_value=Mock(returncode=0)) as run:
            main._extract_archive("mod.7Z")
        command = run.call_args.args[0]
        self.assertIn("-ibck", command)
        self.assertIn("-p-", command)
        self.assertEqual(command[-2:], ["mod.7Z", str(self.destination) + os.sep])

    def test_7zip_uses_its_own_output_argument(self):
        with patch.object(main.tempfile, "mkdtemp", return_value=str(self.destination)), patch.object(
                main, "_find_archive_extractor", return_value=("7zip", "7z.exe")), patch.object(
                main.subprocess, "run", return_value=Mock(returncode=0)) as run:
            main._extract_archive("mod.7z")
        self.assertIn("-o" + str(self.destination), run.call_args.args[0])
        self.assertNotIn("-ibck", run.call_args.args[0])

    def test_unrar_is_not_used_for_7z(self):
        with patch.object(main.os.path, "isfile", side_effect=lambda p: str(p).endswith("UnRAR.exe")), patch.object(
                main.shutil, "which", side_effect=lambda name: "UnRAR.exe" if name == "UnRAR" else None):
            self.assertEqual(main._find_archive_extractor(".7z"), (None, None))
            self.assertEqual(main._find_archive_extractor(".rar")[0], "unrar")

    def test_bundled_reader_handles_rar_and_7z_without_external_programs(self):
        bundled = self.root / "tools" / "7zip" / "7z.exe"
        bundled.parent.mkdir(parents=True)
        bundled.write_bytes(b"fixture")
        with patch.object(main, "RESOURCE_DIR", str(self.root)), \
                patch.object(main.shutil, "which", return_value=None), \
                patch.object(main.os.path, "isfile", side_effect=lambda path: str(path) == str(bundled)), \
                patch.dict(os.environ, {"PATH": ""}):
            for extension in (".rar", ".7z"):
                with self.subTest(extension=extension):
                    self.assertEqual(main._find_archive_extractor(extension), ("7zip", str(bundled)))

    def test_bundled_reader_takes_precedence_over_other_installations(self):
        bundled = os.path.join(str(self.root), "tools", "7zip", "7z.exe")
        with patch.object(main, "RESOURCE_DIR", str(self.root)), \
                patch.object(main.shutil, "which", return_value="external.exe"), \
                patch.object(main.os.path, "isfile", return_value=True):
            self.assertEqual(main._find_archive_extractor(".rar"), ("7zip", bundled))

    def test_extraction_warning_does_not_allow_incomplete_import(self):
        with patch.object(main.tempfile, "mkdtemp", return_value=str(self.destination)), patch.object(
                main, "_find_archive_extractor", return_value=("winrar", "WinRAR.exe")), patch.object(
                main.subprocess, "run", return_value=Mock(returncode=1)):
            with self.assertRaisesRegex(RuntimeError, "completamente"):
                main._extract_archive("mod.7z")
        self.assertFalse(self.destination.exists())

    def test_missing_extractor_has_actionable_error(self):
        with patch.object(main.tempfile, "mkdtemp", return_value=str(self.destination)), patch.object(
                main, "_find_archive_extractor", return_value=(None, None)):
            with self.assertRaisesRegex(RuntimeError, "pacote completo do CrabVault"):
                main._extract_archive("mod.7z")

    def test_selection_accepts_mixed_archive_formats_and_retains_originals(self):
        originals = [str(self.root / name) for name in ("one.7Z", "two.zip", "three.rar")]
        for path in originals:
            pathlib.Path(path).write_bytes(b"original")
        def extract(path):
            folder = self.destination / pathlib.Path(path).stem
            folder.mkdir()
            (folder / (pathlib.Path(path).stem + ".pak")).write_bytes(b"pak")
            return str(folder)
        window = Mock()
        window.create_file_dialog.return_value = originals
        suggestion = {"type": "Mesh", "character": "Hela", "skin": "Default"}
        with patch.object(main, "window", window), patch.object(main, "_extract_archive", side_effect=extract), patch.object(
                main.mod_ops, "analyze_mod_files", return_value=suggestion):
            result = main.Api().begin_mod_install()
        self.assertTrue(result["ok"])
        self.assertEqual(result["file_count"], 3)
        self.assertIn("*.7z", window.create_file_dialog.call_args.kwargs["file_types"][0])
        pending = main.pending_imports[result["token"]]
        self.assertEqual(pending["archives"], originals)
        self.assertEqual(len(pending["component_labels"]), 3)
        self.assertTrue(all(pathlib.Path(p).read_bytes() == b"original" for p in originals))

    def test_failure_in_second_archive_cleans_first_extraction(self):
        window = Mock()
        window.create_file_dialog.return_value = ["one.7z", "two.7z"]
        with patch.object(main, "window", window), patch.object(main, "_extract_archive", side_effect=[
                str(self.destination), RuntimeError("broken")]), patch.object(main.traceback, "print_exc"):
            result = main.Api().begin_mod_install()
        self.assertFalse(result["ok"])
        self.assertFalse(self.destination.exists())
        self.assertFalse(main.pending_imports)

    def test_archive_with_only_blend_is_reported_by_name(self):
        (self.destination / "Jubilee.blend").write_bytes(b"blend")
        window = Mock()
        window.create_file_dialog.return_value = ["Jubilee.7z"]
        with patch.object(main, "window", window), patch.object(main, "_extract_archive", return_value=str(
                self.destination)), patch.object(main.traceback, "print_exc"):
            result = main.Api().begin_mod_install()
        self.assertFalse(result["ok"])
        self.assertIn("Jubilee.7z", result["error"])
        self.assertIn("instaláveis", result["error"])
        self.assertFalse(main.pending_imports)


if __name__ == "__main__":
    unittest.main()

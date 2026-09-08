import base64
import io
import os
import pathlib
import tempfile
import unittest
from unittest.mock import patch

from backend import mod_ops, storage


class LazyDetailPreviewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = pathlib.Path(temporary.name)
        patches = patch.multiple(storage, MODS_JSON=str(self.root / "mods.json"), SETTINGS_FILE=str(self.root / "settings.json"),
                                 STORAGE_DIR=str(self.root / "library"), BACKUPS_DIR=str(self.root / "backups"))
        patches.start()
        self.addCleanup(patches.stop)
        storage.ensure_dirs()
        self.private = pathlib.Path(storage.STORAGE_DIR) / "visual"
        self.private.mkdir()
        (self.private / "body.pak").write_bytes(b"package fixture")
        self.record = {"id": "visual", "name": "Visual", "storage_folder": "visual", "folder": "Visual",
                       "enabled": False, "character": "Hela", "skin": "Default", "type": "Mesh", "types": ["Mesh", "Texture"],
                       "files": [{"name": "body.pak"}], "image": "cover.png", "images": ["cover.png", "second.png", "movie.mp4"],
                       "image_titles": {"cover.png": "Capa", "second.png": "Outro ângulo", "movie.mp4": "Vídeo"},
                       "components": [{"id": "body", "name": "Body", "files": [{"name": "body.pak"}],
                                       "enabled": True, "type": "Mesh", "types": ["Mesh", "Texture"]}],
                       "asset_path_cache": {"classification-v1:body": {
                           "signature": mod_ops._component_analysis_signature([str(self.private / "body.pak")]),
                           "paths": ["Marvel/Content/Meshes/SK_Hero.uasset", "Marvel/Content/Textures/T_Hero.uasset"]}}}
        for name in self.record["images"]:
            (self.private / name).write_bytes(("fixture:" + name).encode())
        storage.save_mods([self.record])
        block_tool = patch.object(mod_ops, "_paths_from_bundle", side_effect=AssertionError("detail must not read packages"))
        block_tool.start()
        self.addCleanup(block_tool.stop)

    def test_light_detail_never_decodes_images_or_generates_thumbnails(self):
        before = pathlib.Path(storage.MODS_JSON).read_bytes()
        with patch.object(mod_ops, "_thumbnail_data_url", side_effect=AssertionError("must be lazy")), \
             patch.object(mod_ops, "_image_data_url", side_effect=AssertionError("must not read full image")), \
             patch.object(mod_ops, "_media_data_url", side_effect=AssertionError("must not read full media")):
            detail = mod_ops.get_mod_details("visual", include_previews=False)
        self.assertIsNone(detail["image_url"])
        self.assertEqual(detail["image_urls"], [])
        self.assertEqual([media["name"] for media in detail["gallery_images"]], self.record["images"])
        self.assertEqual([media["title"] for media in detail["gallery_images"]], ["Capa", "Outro ângulo", "Vídeo"])
        self.assertEqual([media["media_type"] for media in detail["gallery_images"]], ["image", "image", "video"])
        self.assertTrue(all(media["url"] is None and media["preview_url"] is None for media in detail["gallery_images"]))
        self.assertTrue(all(media["thumbnail_key"] for media in detail["gallery_images"]))
        self.assertEqual(detail["thumbnail_key"], detail["gallery_images"][0]["thumbnail_key"])
        self.assertEqual(detail["asset_path_cache"], self.record["asset_path_cache"])
        self.assertEqual(detail["components"][0]["types"], ["Mesh", "Texture"])
        self.assertEqual(pathlib.Path(storage.MODS_JSON).read_bytes(), before)
        self.assertFalse((pathlib.Path(storage.STORAGE_DIR) / ".thumbnails").exists())

    def test_light_detail_is_reused_until_catalog_changes(self):
        first = mod_ops.get_mod_details("visual", include_previews=False)
        with patch.object(mod_ops, "_build_mod_details", side_effect=AssertionError("must reuse metadata")):
            second = mod_ops.get_mod_details("visual", include_previews=False)
        self.assertEqual(second["id"], first["id"])
        second["name"] = "Mutação apenas da resposta"
        self.assertEqual(mod_ops.get_mod_details("visual", include_previews=False)["name"], "Visual")

        records = storage.load_mods()
        records[0]["name"] = "Visual atualizado"
        storage.save_mods(records)
        refreshed = mod_ops.get_mod_details("visual", include_previews=False)
        self.assertEqual(refreshed["name"], "Visual atualizado")

    def test_gallery_flag_disables_both_cover_and_gallery_previews(self):
        with patch.object(mod_ops, "_thumbnail_data_url", side_effect=AssertionError("must not decode images")):
            details = mod_ops.list_mods(include_gallery=True, include_thumbnails=False)
        self.assertEqual(len(details[0]["gallery_images"]), 3)
        self.assertTrue(all(item["preview_url"] is None for item in details[0]["gallery_images"]))

    def test_default_detail_remains_compatible_with_eager_previews(self):
        with patch.object(mod_ops, "_thumbnail_data_url", return_value="data:image/jpeg;base64,thumb") as thumbnails:
            detail = mod_ops.get_mod_details("visual")
        self.assertEqual(thumbnails.call_count, 3)  # capa + duas imagens; vídeo não é convertido
        self.assertEqual(detail["image_url"], "data:image/jpeg;base64,thumb")
        self.assertEqual(detail["gallery_images"][1]["preview_url"], "data:image/jpeg;base64,thumb")
        self.assertIsNone(detail["gallery_images"][2]["preview_url"])

    def test_preview_endpoint_loads_only_selected_thumbnail_and_returns_matching_key(self):
        with patch.object(mod_ops, "_thumbnail_data_url", return_value="data:image/jpeg;base64,small") as thumbnail, \
             patch.object(mod_ops, "_media_data_url", side_effect=AssertionError("full media must not load")):
            result = mod_ops.get_gallery_preview("visual", "second.png")
        thumbnail.assert_called_once_with(str(self.private / "second.png"), fallback_original=False)
        self.assertTrue(result["ok"])
        self.assertEqual(result["preview_url"], "data:image/jpeg;base64,small")
        self.assertEqual(result["thumbnail_key"], mod_ops._thumbnail_key(self.private / "second.png"))

    def test_preview_endpoint_does_not_decode_or_read_video(self):
        with patch.object(mod_ops, "_thumbnail_data_url", side_effect=AssertionError("video must not decode")), \
             patch.object(mod_ops, "_image_data_url", side_effect=AssertionError("video must not load")), \
             patch.object(mod_ops, "_media_data_url", side_effect=AssertionError("video must not load")):
            result = mod_ops.get_gallery_preview("visual", "movie.mp4")
        self.assertTrue(result["ok"])
        self.assertIsNone(result["preview_url"])
        self.assertEqual(result["thumbnail_key"], mod_ops._thumbnail_key(self.private / "movie.mp4"))

    def test_invalid_or_foreign_media_is_rejected_before_thumbnail_work(self):
        with patch.object(mod_ops, "_thumbnail_data_url", side_effect=AssertionError("invalid request must not decode")):
            for name in (None, 9, "", "../cover.png", "nested/cover.png", "nested\\cover.png", "body.pak", "foreign.png"):
                with self.subTest(name=name):
                    self.assertFalse(mod_ops.get_gallery_preview("visual", name)["ok"])
            self.assertFalse(mod_ops.get_gallery_preview("missing", "cover.png")["ok"])
            (self.private / "second.png").unlink()
            self.assertFalse(mod_ops.get_gallery_preview("visual", "second.png")["ok"])

    def test_cover_thumbnail_returns_same_revision_as_light_metadata(self):
        expected = mod_ops.list_mods(include_gallery=True, include_thumbnails=False)[0]["thumbnail_key"]
        with patch.object(mod_ops, "_thumbnail_data_url", return_value="data:image/jpeg;base64,small"):
            result = mod_ops.get_mod_thumbnail("visual")
        self.assertEqual(result["thumbnail_key"], expected)
        self.assertEqual(result["image_url"], "data:image/jpeg;base64,small")

    def test_revision_changes_with_source_path_size_or_mtime_without_loading_image(self):
        source = self.private / "cover.png"
        original = mod_ops._thumbnail_key(source)
        self.assertEqual(original, mod_ops._thumbnail_key(source))
        stamp = source.stat()
        os.utime(source, ns=(stamp.st_atime_ns, stamp.st_mtime_ns + 10000000))
        changed_time = mod_ops._thumbnail_key(source)
        self.assertNotEqual(original, changed_time)
        with source.open("ab") as stream:
            stream.write(b"size changed")
        changed_size = mod_ops._thumbnail_key(source)
        self.assertNotEqual(changed_time, changed_size)
        renamed = self.private / "renamed.png"
        source.rename(renamed)
        self.assertNotEqual(changed_size, mod_ops._thumbnail_key(renamed))
        self.assertIsNone(mod_ops._thumbnail_key(source))
        self.assertIsNone(mod_ops._thumbnail_key(self.private))

    def test_source_change_during_preview_is_not_returned_under_an_old_key(self):
        def replace_source(path, **kwargs):
            pathlib.Path(path).write_bytes(b"newer source bytes")
            return "data:image/jpeg;base64,old"
        with patch.object(mod_ops, "_thumbnail_data_url", side_effect=replace_source):
            self.assertFalse(mod_ops.get_gallery_preview("visual", "second.png")["ok"])
            self.assertFalse(mod_ops.get_mod_thumbnail("visual")["ok"])

    def test_unavailable_pillow_never_falls_back_to_full_image_in_lazy_endpoint(self):
        with patch.object(mod_ops, "Image", None), \
             patch.object(mod_ops, "_image_data_url", side_effect=AssertionError("must not return full image")):
            result = mod_ops.get_gallery_preview("visual", "second.png")
        self.assertFalse(result["ok"])
        self.assertIn("miniatura", result["error"])

    @unittest.skipIf(mod_ops.Image is None, "Pillow unavailable")
    def test_corrupt_image_never_falls_back_to_original_payload_in_lazy_endpoint(self):
        with patch.object(mod_ops, "_image_data_url", side_effect=AssertionError("must not return original")):
            result = mod_ops.get_gallery_preview("visual", "second.png")
        self.assertFalse(result["ok"])

    @unittest.skipIf(mod_ops.Image is None, "Pillow unavailable")
    def test_real_temporary_image_generates_only_bounded_thumbnail_using_shared_key(self):
        source = self.private / "second.png"
        with mod_ops.Image.new("RGB", (3200, 2400), "red") as image:
            image.save(source, format="PNG")
        metadata = mod_ops.get_mod_details("visual", include_previews=False)
        key = next(item["thumbnail_key"] for item in metadata["gallery_images"] if item["name"] == "second.png")
        result = mod_ops.get_gallery_preview("visual", "second.png")
        self.assertTrue(result["ok"])
        self.assertEqual(result["thumbnail_key"], key)
        self.assertTrue((pathlib.Path(storage.STORAGE_DIR) / ".thumbnails" / (key + ".jpg")).exists())
        with mod_ops.Image.open(io.BytesIO(base64.b64decode(result["preview_url"].split(",", 1)[1]))) as preview:
            self.assertLessEqual(preview.width, 480)
            self.assertLessEqual(preview.height, 320)
            self.assertEqual(preview.format, "JPEG")
        with patch.object(mod_ops.Image, "open", side_effect=AssertionError("cached preview must not re-decode original")):
            again = mod_ops.get_gallery_preview("visual", "second.png")
        self.assertEqual(again, result)

    def test_background_metadata_refresh_keeps_preview_generation_disabled(self):
        entry = {"name": "nested/MoviesBink/Intro.bk2"}
        record = {"id": "background", "name": "Background", "storage_folder": "background", "enabled": False,
                  "character": "Backgrounds", "install_target": "marvel_content", "type": "Background", "types": ["Background"],
                  "files": [entry], "components": mod_ops._background_components([entry]), "image": "cover.png", "images": ["cover.png"]}
        private = pathlib.Path(storage.STORAGE_DIR) / "background"
        (private / "nested/MoviesBink").mkdir(parents=True)
        (private / "nested/MoviesBink/Intro.bk2").write_bytes(b"temporary cinematic")
        (private / "cover.png").write_bytes(b"temporary image")
        storage.save_mods([record])
        with patch.object(mod_ops, "_thumbnail_data_url", side_effect=AssertionError("background must remain lazy")), \
             patch.object(mod_ops, "_image_data_url", side_effect=AssertionError("must not decode")), \
             patch.object(mod_ops, "_process_pending_background_audio_changes", return_value=None), \
             patch.object(mod_ops, "_sync_background_audio_files", side_effect=AssertionError("no game work")):
            result = mod_ops.get_mod_details("background", include_previews=False)
        self.assertEqual(result["files"][0]["name"], os.path.join("MoviesBink", "Intro.bk2"))
        self.assertEqual(result["gallery_images"][0]["name"], "cover.png")
        self.assertTrue(result["gallery_images"][0]["thumbnail_key"])
        self.assertFalse((pathlib.Path(storage.STORAGE_DIR) / ".thumbnails").exists())


if __name__ == "__main__":
    unittest.main()

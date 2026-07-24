"""Unit tests for Custom Folder Scan functionality."""
import tempfile
import unittest
from pathlib import Path

from llama_data import DataPaths, LibraryStore, LocalModel
from app.services.library_scan import (
    CustomScanOptions,
    CustomScanProgress,
    scan_custom_folder,
)


class TestCustomFolderScan(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root_path = Path(self.tmp_dir.name)
        self.paths = DataPaths(
            data_dir=self.root_path,
            config_path=self.root_path / "config.json",
            profiles_path=self.root_path / "profiles.json",
            library_path=self.root_path / "library.json",
            cards_dir=self.root_path / "cards",
            schema_cache_path=self.root_path / "schema_cache.json",
            chat_sessions_path=self.root_path / "chat_sessions.json",
            chat_templates_path=self.root_path / "chat_templates.json",
        )
        self.library = LibraryStore(self.paths)

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_custom_scan_basic_and_merge(self):
        # Pre-existing entry in library
        existing_model = LocalModel(id="/existing/model.gguf", path="/existing/model.gguf", size_bytes=1000)
        self.library.save([existing_model])

        # Setup scan folder structure
        scan_folder = self.root_path / "scan_target"
        scan_folder.mkdir()

        # Primary runnable model (6MB)
        primary_file = scan_folder / "llama-3-8b-Q4_K_M.gguf"
        primary_file.write_bytes(b"0" * (6 * 1024 * 1024))

        # Companion file (6MB)
        companion_file = scan_folder / "mmproj-model-f16.gguf"
        companion_file.write_bytes(b"0" * (6 * 1024 * 1024))

        # Small file (1MB)
        small_file = scan_folder / "tiny-model.gguf"
        small_file.write_bytes(b"0" * (1 * 1024 * 1024))

        options = CustomScanOptions(
            target_dir=scan_folder,
            recursive=True,
            min_size_mb=5.0,
        )

        progress_history = []
        def progress_cb(p: CustomScanProgress):
            progress_history.append(p.scanned_files)

        res = scan_custom_folder(options, self.library, progress_callback=progress_cb)

        self.assertIsNone(res.error)
        self.assertEqual(res.added, 1)  # Only primary_file added
        self.assertEqual(res.scanned_files, 3)

        # Check library store merge
        all_models = self.library.load()
        self.assertEqual(len(all_models), 2)  # Pre-existing + 1 new custom model
        ids = {m.id for m in all_models}
        self.assertIn("/existing/model.gguf", ids)
        self.assertIn(str(primary_file.resolve()), ids)

    def test_custom_scan_max_depth(self):
        scan_folder = self.root_path / "depth_test"
        level1 = scan_folder / "level1"
        level2 = level1 / "level2"
        level2.mkdir(parents=True)

        f1 = scan_folder / "model_l0.gguf"
        f1.write_bytes(b"0" * (6 * 1024 * 1024))

        f2 = level1 / "model_l1.gguf"
        f2.write_bytes(b"0" * (6 * 1024 * 1024))

        f3 = level2 / "model_l2.gguf"
        f3.write_bytes(b"0" * (6 * 1024 * 1024))

        options = CustomScanOptions(
            target_dir=scan_folder,
            recursive=True,
            max_depth=1,  # Should scan level0 and level1 only
            min_size_mb=5.0,
        )

        res = scan_custom_folder(options, self.library)
        self.assertEqual(res.scanned_files, 2)
        self.assertEqual(res.added, 2)

    def test_custom_scan_excluded_dirs(self):
        scan_folder = self.root_path / "excl_test"
        git_dir = scan_folder / ".git"
        node_dir = scan_folder / "node_modules"
        valid_dir = scan_folder / "valid"

        git_dir.mkdir(parents=True)
        node_dir.mkdir(parents=True)
        valid_dir.mkdir(parents=True)

        (git_dir / "ignored1.gguf").write_bytes(b"0" * (6 * 1024 * 1024))
        (node_dir / "ignored2.gguf").write_bytes(b"0" * (6 * 1024 * 1024))
        (valid_dir / "valid_model.gguf").write_bytes(b"0" * (6 * 1024 * 1024))

        options = CustomScanOptions(
            target_dir=scan_folder,
            recursive=True,
            include_hidden=False,
            excluded_dirs=["node_modules", ".git"],
            min_size_mb=5.0,
        )

        res = scan_custom_folder(options, self.library)
        self.assertEqual(res.scanned_files, 1)
        self.assertEqual(res.added, 1)


if __name__ == "__main__":
    unittest.main()

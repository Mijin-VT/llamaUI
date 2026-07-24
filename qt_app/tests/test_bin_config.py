import tempfile
import unittest
from pathlib import Path

from llama_data import DataPaths, LibraryStore, LocalModel, default_paths
from llama_data.models import _first_bin_config, _first_mmproj



from app.services.library_scan import (
    _companions_for_path,
    _mmproj_for_path,
    _bin_config_for_path,
    parse_bin_config,
    scan_library,
)


class TestBinConfigAutoDetection(unittest.TestCase):

    def test_bin_companion_and_mmproj_detection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            model_dir = Path(tmpdir) / "my_model_dir"
            model_dir.mkdir()

            gguf_file = model_dir / "llama-3-8b-instruct.Q4_K_M.gguf"
            gguf_file.write_bytes(b"GGUF_DUMMY_HEADER")

            mmproj_bin = model_dir / "mmproj-model-f16.bin"
            mmproj_bin.write_bytes(b"MMPROJ_BIN_DUMMY")

            params_bin = model_dir / "params.bin"
            params_bin.write_text("--ctx-size 8192 --n-gpu-layers 33 --temp 0.7 --threads 8", encoding="utf-8")

            companions = _companions_for_path(gguf_file)
            self.assertEqual(len(companions), 2)

            mmproj = _mmproj_for_path(gguf_file)
            self.assertIsNotNone(mmproj)
            self.assertTrue(mmproj.endswith("mmproj-model-f16.bin"))

            bin_cfg_path = _bin_config_for_path(gguf_file)
            self.assertIsNotNone(bin_cfg_path)
            self.assertTrue(bin_cfg_path.endswith("params.bin"))

            parsed = parse_bin_config(Path(bin_cfg_path))
            self.assertEqual(parsed.get("ctx-size"), 8192)
            self.assertEqual(parsed.get("n-gpu-layers"), 33)
            self.assertEqual(parsed.get("temp"), 0.7)
            self.assertEqual(parsed.get("threads"), 8)

    def test_scan_library_records_bin_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            model_dir = root / "model_folder"
            model_dir.mkdir()

            gguf_file = model_dir / "qwen2.5-7b.gguf"
            gguf_file.write_bytes(b"GGUF_HEADER_12345")

            mmproj_bin = model_dir / "mmproj-vision.bin"
            mmproj_bin.write_bytes(b"VISION_PROJ_BIN")

            params_bin = model_dir / "config.bin"
            params_bin.write_text("--ctx-size 16384 --n-gpu-layers 40", encoding="utf-8")

            paths = default_paths(root)
            store = LibraryStore(paths)



            res = scan_library(root, store)
            self.assertEqual(res.added, 1)

            models = list(store.load())
            self.assertEqual(len(models), 1)
            m = models[0]

            self.assertIsNotNone(m.mmproj_path)
            self.assertTrue(m.mmproj_path.endswith("mmproj-vision.bin"))
            self.assertIsNotNone(m.bin_config_path)
            self.assertTrue(m.bin_config_path.endswith("config.bin"))


if __name__ == "__main__":
    unittest.main()

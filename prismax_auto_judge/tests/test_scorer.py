from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config_loader import load_config
from judge_logger import JsonlLogger
from schemas import validate_vlm_output
from scorer import PrismaXScorer


class ScorerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config, self.config_hash = load_config(ROOT / "config.yaml")

    def test_required_main_missing_is_not_pass(self) -> None:
        scorer = PrismaXScorer(self.config, self.config_hash)
        result = scorer.score_episode({
            "episode_id": "missing_main",
            "task_prompt": "",
            "video_paths": {},
            "metadata": {},
        })
        self.assertIn(result["decision"], {"FAIL", "ERROR", "UNCERTAIN"})
        self.assertNotEqual(result["decision"], "PASS")
        self.assertIn("required_view_missing:main", result["hard_fail_reasons"])

    def test_missing_file_video_returns_error_not_pass(self) -> None:
        scorer = PrismaXScorer(self.config, self.config_hash)
        result = scorer.score_episode({
            "episode_id": "bad_path",
            "task_prompt": "",
            "video_paths": {"main": "does_not_exist.mp4"},
            "metadata": {},
        })
        self.assertEqual(result["decision"], "ERROR")
        self.assertFalse(result["should_submit"])

    def test_invalid_vlm_output_rejected(self) -> None:
        valid, data, errors = validate_vlm_output({"pass_probability": 1.2})
        self.assertFalse(valid)
        self.assertIsNone(data)
        self.assertTrue(errors)

    def test_logger_writes_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "log.jsonl"
            logger = JsonlLogger(log_path)
            logger.write({"mode": "dry_run", "decision": {"decision": "UNCERTAIN"}})
            text = log_path.read_text(encoding="utf-8")
            self.assertIn('"mode": "dry_run"', text)
            self.assertIn('"timestamp"', text)


if __name__ == "__main__":
    unittest.main()


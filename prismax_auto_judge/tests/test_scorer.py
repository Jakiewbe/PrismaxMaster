from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config_loader import load_config
from control_adapter import is_review_list_url, parse_episode_id, parse_review_progress, parse_review_url
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
        self.assertIn("form_plan", result)
        checks = result["form_plan"]["pass_fail_checks"]
        self.assertTrue(any(item["value"] is False for item in checks.values()))

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

    def test_form_plan_pass_maps_all_checks_true(self) -> None:
        scorer = PrismaXScorer(self.config, self.config_hash)
        plan = scorer._build_form_plan("PASS", {"quality": 4, "smoothness": 5, "speed": 4, "completion": 5}, [], [], [], 0.92)
        self.assertTrue(plan["can_fill"])
        self.assertEqual(plan["gate_score"], 92)
        self.assertTrue(all(item["value"] is True for item in plan["pass_fail_checks"].values()))
        self.assertEqual(plan["quality_sliders"]["smoothness"]["level"], "Exc")

    def test_reference_page_parsers(self) -> None:
        self.assertEqual(
            parse_review_url("https://app.prismax.ai/data/review/74?upload=273"),
            {"task_id": "74", "upload_id": "273"},
        )
        self.assertTrue(is_review_list_url("https://app.prismax.ai/data/review"))
        self.assertTrue(is_review_list_url("https://app.prismax.ai/data/review/"))
        self.assertFalse(is_review_list_url("https://app.prismax.ai/data/review/74?upload=273"))
        self.assertEqual(parse_episode_id("Episode #14460 1 of 14"), "14460")
        self.assertEqual(parse_review_progress("Episode #14460 1 of 14"), {"current": 1, "total": 14})


if __name__ == "__main__":
    unittest.main()

class VLMClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config, _ = load_config(ROOT / "config.yaml")

    def test_vlm_request_package_renders_prompt_and_features(self) -> None:
        from vlm_client import VLMClient

        client = VLMClient(self.config)
        package = client.build_request_package(
            task_prompt="pick up the cup",
            frame_paths={"main": ["frame_000.jpg", "frame_010.jpg"]},
            video_paths={"main": "video.mp4"},
            features={
                "main": {
                    "black_frame_ratio": 0.01,
                    "freeze_ratio": 0.02,
                    "motion_energy": 3.4,
                    "brightness_mean": 120,
                    "blur_score": 88,
                }
            },
            episode_id="episode_vlm",
        )
        self.assertEqual(package["episode_id"], "episode_vlm")
        self.assertEqual(package["frame_count"], 2)
        self.assertIn("pick up the cup", package["prompt"])
        self.assertIn("black_frame_ratio: 0.01", package["prompt"])
        self.assertEqual(package["cv_features"]["motion_energy"], 3.4)

    def test_vlm_client_exports_request_without_calling_api(self) -> None:
        from vlm_client import VLMClient

        with tempfile.TemporaryDirectory() as tmp:
            self.config["vlm"]["request_dir"] = tmp
            self.config["vlm"]["enabled"] = False
            client = VLMClient(self.config)
            result = client.judge_episode(
                task_prompt="move the block",
                frame_paths={"main": ["frame.jpg"]},
                video_paths={"main": "video.mp4"},
                features={"_aggregate": {"black_frame_ratio": 0, "freeze_ratio": 0, "motion_energy": 1, "brightness_mean": 100, "blur_score": 50}},
                episode_id="episode_export",
            )
            self.assertIsNone(result)
            exported = list(Path(tmp).glob("episode_export_*.json"))
            self.assertEqual(len(exported), 1)
            self.assertIn('"prompt_version": "prismax_vla_v1"', exported[0].read_text(encoding="utf-8"))

class MultiProviderVLMTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config, _ = load_config(ROOT / "config.yaml")

    def test_parse_json_from_markdown_block(self) -> None:
        from vlm_client import VLMClient

        parsed = VLMClient.parse_json_text('```json\n{"confidence": 0.8}\n```')
        self.assertEqual(parsed["confidence"], 0.8)

    def test_deepseek_text_provider_is_blocked_as_primary_by_default(self) -> None:
        from vlm_client import VLMClient

        with tempfile.TemporaryDirectory() as tmp:
            self.config["vlm"]["enabled"] = True
            self.config["vlm"]["provider"] = "deepseek_text"
            self.config["vlm"]["request_dir"] = tmp
            self.config["vlm"]["allow_text_only_primary"] = False
            client = VLMClient(self.config)
            with self.assertRaises(RuntimeError) as ctx:
                client.judge_episode(
                    task_prompt="pick up object",
                    frame_paths={"main": ["missing.jpg"]},
                    video_paths={"main": "video.mp4"},
                    features={"_aggregate": {"black_frame_ratio": 0, "freeze_ratio": 0, "motion_energy": 1, "brightness_mean": 100, "blur_score": 50}},
                    episode_id="deepseek_blocked",
                )
            self.assertIn("Text-only provider cannot be used", str(ctx.exception))
            self.assertEqual(len(list(Path(tmp).glob("deepseek_blocked_*.json"))), 1)

    def test_builtin_provider_profiles_exist(self) -> None:
        vlm_cfg = self.config["vlm"]
        self.assertIn("openai_compatible", vlm_cfg["provider_profiles"])
        self.assertIn("deepseek_text", vlm_cfg["provider_profiles"])
        self.assertIn("xiaomi_compatible", vlm_cfg["provider_profiles"])

class DailyWorkflowPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config, _ = load_config(ROOT / "config.yaml")

    def test_daily_workflow_blocks_when_quota_reached(self) -> None:
        from workflow_policy import DailyWorkflowPolicy

        with tempfile.TemporaryDirectory() as tmp:
            self.config["daily_workflow"]["daily_counts_path"] = "counts.json"
            self.config["daily_workflow"]["max_labels_per_day"] = 1
            policy = DailyWorkflowPolicy(self.config, tmp)
            policy.record_vla_result(True)
            allowed, reason = policy.can_attempt_vla()
            self.assertFalse(allowed)
            self.assertIn("daily_vla_quota_reached", reason)

    def test_daily_workflow_allows_missing_control_state_by_default(self) -> None:
        from workflow_policy import DailyWorkflowPolicy

        with tempfile.TemporaryDirectory() as tmp:
            self.config["daily_workflow"]["control_state_file"] = "missing.json"
            self.config["daily_workflow"]["block_if_control_state_missing"] = False
            policy = DailyWorkflowPolicy(self.config, tmp)
            allowed, reason = policy.is_control_ready()
            self.assertTrue(allowed)
            self.assertIn("control_state_missing_but_not_blocking", reason)

    def test_daily_workflow_blocks_missing_control_state_in_default_config(self) -> None:
        from workflow_policy import DailyWorkflowPolicy

        with tempfile.TemporaryDirectory() as tmp:
            self.config["daily_workflow"]["control_state_file"] = "missing.json"
            policy = DailyWorkflowPolicy(self.config, tmp)
            allowed, reason = policy.is_control_ready()
            self.assertFalse(allowed)
            self.assertIn("control_state_missing", reason)

    def test_daily_workflow_requires_six_control_operations(self) -> None:
        from workflow_policy import DailyWorkflowPolicy

        with tempfile.TemporaryDirectory() as tmp:
            state_path = Path(tmp) / "state.json"
            state_path.write_text('{"totalOperations": 5}', encoding="utf-8")
            self.config["daily_workflow"]["control_state_file"] = "state.json"
            policy = DailyWorkflowPolicy(self.config, tmp)
            allowed, reason = policy.is_control_ready()
            self.assertFalse(allowed)
            self.assertIn("5/6", reason)

            state_path.write_text('{"totalOperations": 6}', encoding="utf-8")
            allowed, reason = policy.is_control_ready()
            self.assertTrue(allowed)
            self.assertIn("6/6", reason)




class MainModeTests(unittest.TestCase):
    def test_auto_limited_mode_is_supported(self) -> None:
        from main import VALID_MODES

        self.assertIn("auto_limited", VALID_MODES)

    def test_auto_limited_keeps_fail_submit_disabled_by_default(self) -> None:
        from main import apply_local_mode

        control, count = apply_local_mode(
            {"decision": "FAIL", "should_submit": True},
            "auto_limited",
            {"safety": {"allow_auto_fail_submit": False, "max_auto_submit_per_run": 10}},
            0,
        )
        self.assertFalse(control["submitted"])
        self.assertEqual(control["submit_status"], "auto_fail_submit_disabled")
        self.assertEqual(count, 0)


class ControlAdapterUnitTests(unittest.TestCase):
    def test_extract_task_prompt_from_page_text(self) -> None:
        from control_adapter import PrismaXControlAdapter

        adapter = PrismaXControlAdapter({})
        text = "Episode #1\nTask Prompt\npick up the cup and place it on the plate\nOther"
        self.assertEqual(adapter._extract_task_prompt(text), "pick up the cup and place it on the plate")


class ConservativeVlaConfigTests(unittest.TestCase):
    def test_live_capture_uses_more_frames_and_waits_for_ready_video(self) -> None:
        config, _ = load_config(ROOT / "config.yaml")
        live = config["live_capture"]
        self.assertGreaterEqual(len(live["percent_points"]), 12)
        self.assertGreaterEqual(live["wait_until_ready_seconds"], 8)
        self.assertGreaterEqual(live["min_nonblack_ratio"], 0.70)
        self.assertGreaterEqual(config["vlm"]["max_images"], 30)

    def test_auto_decision_thresholds_are_conservative(self) -> None:
        config, _ = load_config(ROOT / "config.yaml")
        thresholds = config["decision_thresholds"]
        self.assertGreaterEqual(thresholds["auto_pass_min_probability"], 0.85)
        self.assertLessEqual(thresholds["auto_fail_max_probability"], 0.15)
        self.assertGreaterEqual(thresholds["min_confidence_submit"], 0.85)


class LiveWorkflowStepTests(unittest.TestCase):
    def test_readonly_live_steps_are_documented_for_workflow_bypass(self) -> None:
        from main import run_live_once

        source_names = run_live_once.__code__.co_consts
        self.assertIn("open-review", str(source_names))
        self.assertIn("capture", str(source_names))
        self.assertIn("return-arm", str(source_names))

    def test_control_adapter_uses_page_screenshot_capture_helpers(self) -> None:
        from control_adapter import PrismaXControlAdapter

        self.assertTrue(hasattr(PrismaXControlAdapter, "_seek_video_and_get_clip"))
        self.assertTrue(hasattr(PrismaXControlAdapter, "_image_nonblack_ratio"))

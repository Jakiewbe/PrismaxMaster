from __future__ import annotations

import base64
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import requests


class VLMClient:
    """Multi-provider VLM client with safe defaults.

    Supported providers:
      - manual: export request package only, no API call.
      - openai_compatible: chat-completions API with image_url parts.
      - deepseek_text: text-only review mode; disabled for primary visual scoring
        unless allow_text_only_primary is true.
      - xiaomi_compatible: OpenAI-compatible endpoint configured by base_url/api key.
    """

    def __init__(self, config: dict[str, Any]):
        self.config = config
        vlm_cfg = config.get("vlm", {})
        self.provider = vlm_cfg.get("provider", "manual")
        self.provider_profiles = vlm_cfg.get("provider_profiles", {})
        self.profile = self._resolve_profile(self.provider)
        self.model_name = vlm_cfg.get("model") or self.profile.get("model")
        self.prompt_version = vlm_cfg.get("prompt_version", "prismax_vla_v1")
        self.last_request_path: str | None = None
        self.last_response_path: str | None = None

    def judge_episode(
        self,
        task_prompt: str,
        frame_paths: dict[str, list[str]],
        video_paths: dict[str, str] | None = None,
        features: dict[str, Any] | None = None,
        episode_id: str | None = None,
    ) -> dict[str, Any] | None:
        request = self.build_request_package(
            task_prompt=task_prompt,
            frame_paths=frame_paths,
            video_paths=video_paths or {},
            features=features or {},
            episode_id=episode_id,
        )
        if self.config.get("vlm", {}).get("export_requests", True):
            self.last_request_path = str(self.export_request_package(request))
        if not self.config.get("vlm", {}).get("enabled", False):
            return None
        if self.provider == "manual":
            return None
        if self.provider == "deepseek_text" or self.profile.get("text_only"):
            return self._call_text_only_provider(request)
        return self._call_openai_compatible_provider(request)

    def build_request_package(
        self,
        task_prompt: str,
        frame_paths: dict[str, list[str]],
        video_paths: dict[str, str],
        features: dict[str, Any],
        episode_id: str | None = None,
    ) -> dict[str, Any]:
        aggregate = self._aggregate_features(features)
        flat_frames = self._flatten_frames(frame_paths)
        prompt = self.render_prompt(
            task_prompt=task_prompt,
            frame_count=len(flat_frames),
            aggregate_features=aggregate,
        )
        return {
            "episode_id": episode_id or "unknown",
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "provider": self.provider,
            "model": self.model_name,
            "prompt_version": self.prompt_version,
            "prompt": prompt,
            "task_prompt": task_prompt,
            "frame_count": len(flat_frames),
            "frames": frame_paths,
            "frame_attachments": flat_frames,
            "video_paths": video_paths,
            "cv_features": aggregate,
            "raw_features": features,
            "expected_response_schema": self.expected_response_schema(),
        }

    @staticmethod
    def expected_response_schema() -> dict[str, str]:
        return {
            "task_matches_prompt": "boolean",
            "task_success_score": "0-100 number",
            "completion_score": "0-100 number",
            "final_state_score": "0-100 number",
            "trajectory_clarity_score": "0-100 number",
            "smoothness_score": "0-100 number",
            "speed_score": "0-100 number",
            "diversity_score": "0-100 number",
            "no_damage_score": "0-100 number",
            "failure_detected": "boolean",
            "failure_modes": "list[str]",
            "destructive_action": "boolean",
            "long_stuck_or_struggle": "boolean",
            "pass_probability": "0.0-1.0 number",
            "confidence": "0.0-1.0 number",
            "reason": "one sentence",
        }

    def render_prompt(self, task_prompt: str, frame_count: int, aggregate_features: dict[str, float]) -> str:
        template = self._load_prompt_template()
        replacements = {
            "{task_prompt}": task_prompt or "",
            "{frame_count}": str(frame_count),
            "{black_frame_ratio:.2f}": f"{aggregate_features.get('black_frame_ratio', 0.0):.2f}",
            "{freeze_ratio:.2f}": f"{aggregate_features.get('freeze_ratio', 0.0):.2f}",
            "{motion_energy:.2f}": f"{aggregate_features.get('motion_energy', 0.0):.2f}",
            "{brightness_mean:.0f}": f"{aggregate_features.get('brightness_mean', 0.0):.0f}",
            "{blur_score:.0f}": f"{aggregate_features.get('blur_score', 0.0):.0f}",
        }
        for needle, value in replacements.items():
            template = template.replace(needle, value)
        return template

    def export_request_package(self, request: dict[str, Any]) -> Path:
        request_dir = self._resolve_package_path(self.config.get("vlm", {}).get("request_dir", "data/logs/vlm_requests"))
        request_dir.mkdir(parents=True, exist_ok=True)
        episode_id = self._safe_file_token(str(request.get("episode_id") or "unknown"))
        out_path = request_dir / f"{episode_id}_{int(time.time())}.json"
        out_path.write_text(json.dumps(request, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        return out_path

    def export_response_package(self, episode_id: str, response: dict[str, Any]) -> Path:
        response_dir = self._resolve_package_path(self.config.get("vlm", {}).get("response_dir", "data/logs/vlm_responses"))
        response_dir.mkdir(parents=True, exist_ok=True)
        out_path = response_dir / f"{self._safe_file_token(episode_id)}_{int(time.time())}.json"
        out_path.write_text(json.dumps(response, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        self.last_response_path = str(out_path)
        return out_path

    def _call_openai_compatible_provider(self, request: dict[str, Any]) -> dict[str, Any]:
        base_url = self._required_profile_value("base_url")
        api_key = self._api_key()
        model = self.model_name or self._required_profile_value("model")
        timeout = int(self.config.get("vlm", {}).get("timeout_seconds", 90))
        max_retries = int(self.config.get("vlm", {}).get("max_retries", 2))
        payload = {
            "model": model,
            "temperature": float(self.config.get("vlm", {}).get("temperature", 0.0)),
            "messages": [
                {
                    "role": "user",
                    "content": self._build_multimodal_content(request),
                }
            ],
        }
        if self.profile.get("response_format_json", True):
            payload["response_format"] = {"type": "json_object"}
        return self._post_chat_completion(base_url, api_key, payload, timeout, max_retries, request)

    def _call_text_only_provider(self, request: dict[str, Any]) -> dict[str, Any]:
        if not self.config.get("vlm", {}).get("allow_text_only_primary", False):
            raise RuntimeError(
                "Text-only provider cannot be used as primary VLA scorer. "
                "Use a multimodal provider, or set vlm.allow_text_only_primary=true knowingly."
            )
        base_url = self._required_profile_value("base_url")
        api_key = self._api_key()
        model = self.model_name or self._required_profile_value("model")
        timeout = int(self.config.get("vlm", {}).get("timeout_seconds", 90))
        max_retries = int(self.config.get("vlm", {}).get("max_retries", 2))
        text = (
            request["prompt"]
            + "\n\nFrame paths are listed below, but this provider cannot inspect images directly. "
            + "Only answer if the provided text is sufficient; otherwise return low confidence.\n"
            + json.dumps(request.get("frame_attachments", []), ensure_ascii=False)
        )
        payload = {
            "model": model,
            "temperature": float(self.config.get("vlm", {}).get("temperature", 0.0)),
            "messages": [{"role": "user", "content": text}],
            "response_format": {"type": "json_object"},
        }
        return self._post_chat_completion(base_url, api_key, payload, timeout, max_retries, request)

    def _post_chat_completion(
        self,
        base_url: str,
        api_key: str,
        payload: dict[str, Any],
        timeout: int,
        max_retries: int,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        last_error: Exception | None = None
        endpoint = base_url.rstrip("/")
        for attempt in range(max_retries + 1):
            try:
                response = requests.post(endpoint, headers=headers, json=payload, timeout=timeout)
                if response.status_code >= 500 and attempt < max_retries:
                    time.sleep(1 + attempt)
                    continue
                response.raise_for_status()
                raw = response.json()
                self.export_response_package(str(request.get("episode_id") or "unknown"), raw)
                return self._extract_json_from_chat_response(raw)
            except Exception as exc:
                last_error = exc
                if attempt < max_retries:
                    time.sleep(1 + attempt)
                    continue
                break
        raise RuntimeError(f"VLM provider call failed: {last_error}")

    def _build_multimodal_content(self, request: dict[str, Any]) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = [{"type": "text", "text": request["prompt"]}]
        max_images = int(self.config.get("vlm", {}).get("max_images", 20))
        for item in request.get("frame_attachments", [])[:max_images]:
            path = Path(item["path"])
            if not path.exists():
                continue
            mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:{mime};base64,{encoded}"},
            })
        if len(content) == 1:
            raise RuntimeError("No frame images found for multimodal VLM request")
        return content

    @staticmethod
    def _extract_json_from_chat_response(raw: dict[str, Any]) -> dict[str, Any]:
        try:
            text = raw["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("Unexpected chat completion response shape") from exc
        if isinstance(text, list):
            text = "".join(str(part.get("text", "")) if isinstance(part, dict) else str(part) for part in text)
        if not isinstance(text, str):
            raise RuntimeError("Chat completion content is not text")
        return VLMClient.parse_json_text(text)

    @staticmethod
    def parse_json_text(text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            start = cleaned.find("{")
            end = cleaned.rfind("}")
            if start == -1 or end == -1 or end <= start:
                raise
            return json.loads(cleaned[start:end + 1])

    def _load_prompt_template(self) -> str:
        path = self._resolve_package_path(self.config.get("vlm", {}).get("prompt_template", "vlm_prompts/prismax_vla_v1.txt"))
        if not path.exists():
            raise FileNotFoundError(f"VLM prompt template not found: {path}")
        return path.read_text(encoding="utf-8")

    def _resolve_profile(self, provider: str) -> dict[str, Any]:
        profiles = self.config.get("vlm", {}).get("provider_profiles", {})
        if provider in profiles:
            return dict(profiles[provider])
        builtins = {
            "openai_compatible": {
                "base_url": "https://api.openai.com/v1/chat/completions",
                "api_key_env": "OPENAI_API_KEY",
                "model": "gpt-4o-mini",
                "response_format_json": True,
            },
            "deepseek_text": {
                "base_url": "https://api.deepseek.com/chat/completions",
                "api_key_env": "DEEPSEEK_API_KEY",
                "model": "deepseek-chat",
                "text_only": True,
                "response_format_json": True,
            },
            "xiaomi_compatible": {
                "base_url": os.environ.get("XIAOMI_VLM_BASE_URL", ""),
                "api_key_env": "XIAOMI_API_KEY",
                "model": os.environ.get("XIAOMI_VLM_MODEL", ""),
                "response_format_json": True,
            },
        }
        return dict(builtins.get(provider, {}))

    def _api_key(self) -> str:
        explicit = self.profile.get("api_key") or self.config.get("vlm", {}).get("api_key")
        if explicit:
            return str(explicit)
        env_name = self.profile.get("api_key_env") or self.config.get("vlm", {}).get("api_key_env")
        if env_name and os.environ.get(str(env_name)):
            return str(os.environ[str(env_name)])
        raise RuntimeError(f"Missing API key for provider {self.provider}")

    def _required_profile_value(self, key: str) -> str:
        value = self.profile.get(key) or self.config.get("vlm", {}).get(key)
        if value:
            return str(value)
        raise RuntimeError(f"Missing VLM provider config: {key}")

    @staticmethod
    def _flatten_frames(frame_paths: dict[str, list[str]]) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for view_name, paths in frame_paths.items():
            for index, path in enumerate(paths, start=1):
                output.append({"view": view_name, "index": index, "path": path})
        return output

    @staticmethod
    def _aggregate_features(features: dict[str, Any]) -> dict[str, float]:
        if isinstance(features.get("_aggregate"), dict):
            source = features["_aggregate"]
        else:
            views = [v for k, v in features.items() if not str(k).startswith("_") and isinstance(v, dict)]
            source = {}
            for key in ["black_frame_ratio", "freeze_ratio", "motion_energy", "brightness_mean", "blur_score"]:
                values = [float(v[key]) for v in views if isinstance(v.get(key), (int, float))]
                if not values:
                    source[key] = 0.0
                elif key in {"black_frame_ratio", "freeze_ratio"}:
                    source[key] = max(values)
                elif key in {"motion_energy", "blur_score"}:
                    source[key] = sum(values) / len(values)
                else:
                    source[key] = sum(values) / len(values)
        return {
            "black_frame_ratio": float(source.get("black_frame_ratio", 0.0) or 0.0),
            "freeze_ratio": float(source.get("freeze_ratio", 0.0) or 0.0),
            "motion_energy": float(source.get("motion_energy", 0.0) or 0.0),
            "brightness_mean": float(source.get("brightness_mean", 0.0) or 0.0),
            "blur_score": float(source.get("blur_score", 0.0) or 0.0),
        }

    @staticmethod
    def _resolve_package_path(path: str | Path) -> Path:
        path_obj = Path(path)
        if path_obj.is_absolute():
            return path_obj
        return Path(__file__).resolve().parent / path_obj

    @staticmethod
    def _safe_file_token(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)[:120] or "unknown"

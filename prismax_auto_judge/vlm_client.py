from __future__ import annotations

from typing import Any


class VLMClient:
    """Empty VLM adapter for v0.

    Later model providers should be wired here and return the schema validated in
    schemas.validate_vlm_output().
    """

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.model_name = None
        self.prompt_version = None

    def judge_episode(
        self,
        task_prompt: str,
        frame_paths: dict[str, list[str]],
        video_paths: dict[str, str] | None = None,
    ) -> dict[str, Any] | None:
        return None


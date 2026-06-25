from __future__ import annotations

from pathlib import Path
from typing import Any, Iterator

from video_features import VIDEO_EXTENSIONS


class PrismaXControlAdapter:
    """Page control placeholder.

    v0 intentionally does not automate the live PrismaX page. Local dry-run is
    implemented now; browser filling/submission should be added here later.
    """

    def __init__(self, config: dict[str, Any]):
        self.config = config

    def open_page(self) -> None:
        raise NotImplementedError("Live page control is not implemented in v0")

    def get_current_episode(self) -> dict[str, Any] | None:
        raise NotImplementedError("Live page control is not implemented in v0")

    def get_episode_id(self) -> str | None:
        raise NotImplementedError("Live page control is not implemented in v0")

    def fill_result(self, result: dict[str, Any]) -> None:
        raise NotImplementedError("Live page control is not implemented in v0")

    def skip_episode(self, reason: str = "") -> None:
        raise NotImplementedError("Live page control is not implemented in v0")

    def next_episode(self) -> None:
        raise NotImplementedError("Live page control is not implemented in v0")

    def submit(self) -> None:
        raise NotImplementedError("Live page control is not implemented in v0")

    def abort_submit(self, reason: str) -> None:
        raise RuntimeError(f"submit_aborted:{reason}")


def iter_local_episodes(video_dir: str | Path) -> Iterator[dict[str, Any]]:
    root = Path(video_dir)
    if not root.exists():
        return

    grouped: dict[str, dict[str, str]] = {}
    for path in sorted(root.iterdir()):
        if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        stem = path.stem
        episode_id = stem
        view = "main"
        for suffix, view_name in [("_main", "main"), ("_left_wrist", "left_wrist"), ("_right_wrist", "right_wrist")]:
            if stem.endswith(suffix):
                episode_id = stem[: -len(suffix)]
                view = view_name
                break
        grouped.setdefault(episode_id, {})[view] = str(path)

    for episode_id, paths in grouped.items():
        yield {
            "episode_id": episode_id,
            "task_prompt": "",
            "video_paths": paths,
            "metadata": {"source": "local_folder"},
        }


from __future__ import annotations

from pathlib import Path
from typing import Any


def _cv2():
    try:
        import cv2  # type: ignore

        return cv2
    except ModuleNotFoundError as exc:
        raise RuntimeError("opencv-python is required for frame sampling") from exc


def sample_video_frames(
    video_path: str | Path,
    output_dir: str | Path,
    view_name: str,
    percent_points: list[int],
    extra_frame_indices: list[int | None] | None = None,
) -> list[str]:
    cv2 = _cv2()
    path = Path(video_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot_read_video:{path}")
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if frame_count <= 0:
        cap.release()
        return []

    indices: set[int] = set()
    for pct in percent_points:
        pct = max(0, min(100, int(pct)))
        indices.add(round((frame_count - 1) * pct / 100))
    for idx in extra_frame_indices or []:
        if idx is not None:
            indices.add(max(0, min(frame_count - 1, int(idx))))

    saved: list[str] = []
    for idx in sorted(indices):
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        out_path = out_dir / f"{view_name}_{idx:06d}.jpg"
        cv2.imwrite(str(out_path), frame)
        saved.append(str(out_path))

    cap.release()
    return saved


def sample_episode_frames(episode: dict[str, Any], features: dict[str, Any], config: dict[str, Any]) -> dict[str, list[str]]:
    sampling_cfg = config.get("frame_sampling", {})
    percent_points = sampling_cfg.get("percent_points", [0, 10, 25, 50, 75, 90, 100])
    frames_root = Path(__file__).resolve().parent / "data" / "frames" / str(episode.get("episode_id", "unknown"))
    output: dict[str, list[str]] = {}

    for view_name, path in (episode.get("video_paths") or {}).items():
        view_features = features.get(view_name, {})
        extras = [
            view_features.get("motion_peak_frame_index"),
            view_features.get("long_idle_start_frame_index"),
            view_features.get("long_idle_end_frame_index"),
        ]
        try:
            output[view_name] = sample_video_frames(path, frames_root, view_name, percent_points, extras)
        except Exception:
            output[view_name] = []
    return output


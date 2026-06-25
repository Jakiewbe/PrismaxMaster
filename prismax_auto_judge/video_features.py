from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi"}


def _cv2():
    try:
        import cv2  # type: ignore

        return cv2
    except ModuleNotFoundError as exc:
        raise RuntimeError("opencv-python is required for video feature extraction") from exc


def analyze_video(path: str | Path, sample_limit: int = 120) -> dict[str, Any]:
    cv2 = _cv2()
    video_path = Path(path)
    if not video_path.exists():
        raise FileNotFoundError(str(video_path))

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot_read_video:{video_path}")

    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
    duration_seconds = frame_count / fps if frame_count > 0 and fps > 0 else 0
    if frame_count <= 0:
        cap.release()
        return {
            "path": str(video_path),
            "readable": True,
            "frame_count": 0,
            "fps": fps,
            "duration_seconds": duration_seconds,
            "black_frame_ratio": 1.0,
            "freeze_ratio": 1.0,
            "blur_score": 0.0,
            "brightness_mean": 0.0,
            "motion_energy": 0.0,
            "start_end_diff": 0.0,
            "idle_ratio": 1.0,
            "motion_peak_frame_index": None,
            "long_idle_start_frame_index": None,
            "long_idle_end_frame_index": None,
        }

    step = max(1, frame_count // sample_limit)
    frame_indices = list(range(0, frame_count, step))
    if frame_indices[-1] != frame_count - 1:
        frame_indices.append(frame_count - 1)

    grays: list[np.ndarray] = []
    brightness_values: list[float] = []
    blur_values: list[float] = []
    black_count = 0

    for idx in frame_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok or frame is None:
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        grays.append(gray)
        brightness = float(np.mean(gray))
        brightness_values.append(brightness)
        blur_values.append(float(cv2.Laplacian(gray, cv2.CV_64F).var()))
        if brightness < 8:
            black_count += 1

    cap.release()

    if not grays:
        raise RuntimeError(f"no_readable_frames:{video_path}")

    diffs: list[float] = []
    for prev, cur in zip(grays, grays[1:]):
        diffs.append(float(np.mean(cv2.absdiff(prev, cur))))

    motion_energy = float(np.mean(diffs)) if diffs else 0.0
    freeze_ratio = float(sum(1 for d in diffs if d < 1.0) / len(diffs)) if diffs else 1.0
    idle_threshold = max(1.0, motion_energy * 0.35)
    idle_ratio = float(sum(1 for d in diffs if d <= idle_threshold) / len(diffs)) if diffs else 1.0
    start_end_diff = float(np.mean(cv2.absdiff(grays[0], grays[-1]))) if len(grays) > 1 else 0.0

    motion_peak_frame_index = None
    if diffs:
        peak_sample_idx = int(np.argmax(np.array(diffs))) + 1
        motion_peak_frame_index = frame_indices[min(peak_sample_idx, len(frame_indices) - 1)]

    long_idle_start = None
    long_idle_end = None
    current_start = None
    longest = (0, None, None)
    for i, diff in enumerate(diffs):
        if diff <= idle_threshold:
            if current_start is None:
                current_start = i
        elif current_start is not None:
            length = i - current_start
            if length > longest[0]:
                longest = (length, current_start, i)
            current_start = None
    if current_start is not None:
        length = len(diffs) - current_start
        if length > longest[0]:
            longest = (length, current_start, len(diffs))
    if longest[1] is not None and longest[2] is not None:
        long_idle_start = frame_indices[longest[1]]
        long_idle_end = frame_indices[min(longest[2], len(frame_indices) - 1)]

    return {
        "path": str(video_path),
        "readable": True,
        "frame_count": frame_count,
        "fps": fps,
        "duration_seconds": duration_seconds,
        "black_frame_ratio": float(black_count / len(grays)),
        "freeze_ratio": freeze_ratio,
        "blur_score": float(np.mean(blur_values)) if blur_values else 0.0,
        "brightness_mean": float(np.mean(brightness_values)) if brightness_values else 0.0,
        "motion_energy": motion_energy,
        "start_end_diff": start_end_diff,
        "idle_ratio": idle_ratio,
        "motion_peak_frame_index": motion_peak_frame_index,
        "long_idle_start_frame_index": long_idle_start,
        "long_idle_end_frame_index": long_idle_end,
    }


def analyze_episode_videos(episode: dict[str, Any], config: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    features: dict[str, Any] = {}
    errors: list[str] = []
    video_paths = episode.get("video_paths") or {}
    views = config.get("views", {})

    for view_name, view_cfg in views.items():
        path = video_paths.get(view_name)
        if not path:
            features[view_name] = {"present": False, "required": bool(view_cfg.get("required"))}
            if view_cfg.get("required") and view_cfg.get("hard_fail_if_missing", False):
                errors.append(f"required_view_missing:{view_name}")
            continue
        try:
            view_features = analyze_video(path)
            view_features["present"] = True
            view_features["required"] = bool(view_cfg.get("required"))
            features[view_name] = view_features
        except Exception as exc:
            features[view_name] = {
                "present": True,
                "required": bool(view_cfg.get("required")),
                "path": str(path),
                "error": str(exc),
            }
            errors.append(f"video_error:{view_name}:{exc}")

    return features, errors


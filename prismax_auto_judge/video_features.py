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


def play_video(
    path: str | Path,
    speed_multiplier: float = 8.0,
    sample_every_n_frames: int = 3,
    simulate_delay: bool = True,
) -> dict[str, Any]:
    """Simulate video playback: read frames sequentially, build time-series features.

    Unlike analyze_video() which jumps to sample points, this walks through the
    video frame-by-frame (with configurable skip) to mimic a human watching.

    Returns global features + timeline data for segment-level anomaly detection.
    """
    import time as _time

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
        return _empty_playback_result(str(video_path), fps, duration_seconds)

    # ── sequential playback ──────────────────────────────────
    frame_indices = list(range(0, frame_count, sample_every_n_frames))
    if frame_indices[-1] != frame_count - 1:
        frame_indices.append(frame_count - 1)

    grays: list[np.ndarray] = []
    brightness_series: list[float] = []
    blur_series: list[float] = []
    diff_series: list[float] = []
    black_count = 0
    prev_gray: np.ndarray | None = None
    real_elapsed = 0.0
    total_processed = 0

    _t0 = _time.monotonic()
    for idx in frame_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        ok, frame = cap.read()
        if not ok or frame is None:
            continue

        total_processed += 1
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        grays.append(gray)

        brightness = float(np.mean(gray))
        brightness_series.append(brightness)
        blur_series.append(float(cv2.Laplacian(gray, cv2.CV_64F).var()))

        if brightness < 8:
            black_count += 1

        if prev_gray is not None:
            diff = float(np.mean(cv2.absdiff(prev_gray, gray)))
            diff_series.append(diff)
        prev_gray = gray

        # Simulate real-time playback delay
        if simulate_delay:
            frame_time = (sample_every_n_frames / max(fps, 1)) / speed_multiplier
            real_elapsed += frame_time
            target = _t0 + real_elapsed
            wait = target - _time.monotonic()
            if wait > 0:
                _time.sleep(min(wait, 0.05))  # cap at 50ms per iteration

    cap.release()

    if not grays:
        raise RuntimeError(f"no_readable_frames:{video_path}")

    # ── timeline analysis ────────────────────────────────────
    timeline = _build_timeline(brightness_series, blur_series, diff_series, fps, sample_every_n_frames)

    # ── global features ──────────────────────────────────────
    global_features = _compute_global_features(
        grays, brightness_series, blur_series, diff_series,
        black_count, frame_count, fps, duration_seconds, str(video_path)
    )

    global_features["path"] = str(video_path)
    global_features["readable"] = True
    global_features["frame_count"] = frame_count
    global_features["fps"] = fps
    global_features["duration_seconds"] = duration_seconds
    global_features["playback_frames_processed"] = total_processed
    global_features["playback_speed"] = speed_multiplier

    return {
        **global_features,
        "timeline": timeline,
    }


def _empty_playback_result(path: str, fps: float, duration: float) -> dict[str, Any]:
    return {
        "path": path,
        "readable": True,
        "frame_count": 0,
        "fps": fps,
        "duration_seconds": duration,
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
        "playback_frames_processed": 0,
        "playback_speed": 1.0,
        "timeline": {"segments": [], "anomaly_intervals": []},
    }


def _build_timeline(
    brightness: list[float],
    blur: list[float],
    diffs: list[float],
    fps: float,
    sample_every_n: int,
) -> dict[str, Any]:
    """Split the video timeline into temporal segments and detect anomaly intervals."""
    n = len(brightness)
    if n < 2:
        return {"segments": [], "anomaly_intervals": [], "total_samples": n}

    # Divide into ~5 temporal chunks for segment analysis
    chunk_size = max(2, n // 5)
    segments = []
    anomalies = []

    for chunk_start in range(0, n, chunk_size):
        chunk_end = min(chunk_start + chunk_size, n)
        if chunk_end - chunk_start < 2:
            continue
        chunk_b = brightness[chunk_start:chunk_end]
        chunk_bl = blur[chunk_start:chunk_end]
        # diffs has one fewer element (diff between consecutive frames)
        d_start = max(0, chunk_start - 1)
        d_end = min(len(diffs), chunk_end - 1)
        chunk_d = diffs[d_start:d_end] if d_end > d_start else [0.0]

        seg = {
            "start_sec": round(chunk_start * sample_every_n / max(fps, 1), 1),
            "end_sec": round(chunk_end * sample_every_n / max(fps, 1), 1),
            "brightness_mean": float(np.mean(chunk_b)) if chunk_b else 0.0,
            "blur_mean": float(np.mean(chunk_bl)) if chunk_bl else 0.0,
            "motion_mean": float(np.mean(chunk_d)) if chunk_d else 0.0,
            "black_ratio": float(sum(1 for b in chunk_b if b < 8) / len(chunk_b)) if chunk_b else 0.0,
            "freeze_ratio": float(sum(1 for d in chunk_d if d < 1.0) / len(chunk_d)) if chunk_d else 1.0,
        }
        segments.append(seg)

        # Detect anomaly intervals
        if seg["black_ratio"] > 0.5 or seg["freeze_ratio"] > 0.8 or seg["motion_mean"] < 0.3:
            anomalies.append({
                "type": "timeline_anomaly",
                "start_sec": seg["start_sec"],
                "end_sec": seg["end_sec"],
                "black_ratio": seg["black_ratio"],
                "freeze_ratio": seg["freeze_ratio"],
                "motion_mean": seg["motion_mean"],
            })

    return {
        "segments": segments,
        "anomaly_intervals": anomalies,
        "total_samples": n,
        "chunk_size": chunk_size,
    }


def _compute_global_features(
    grays: list[np.ndarray],
    brightness: list[float],
    blur: list[float],
    diffs: list[float],
    black_count: int,
    frame_count: int,
    fps: float,
    duration: float,
    path: str,
) -> dict[str, Any]:
    """Compute global features from sequential playback data (reuses analyze_video logic)."""
    cv2_mod = _cv2()
    n = len(grays)

    motion_energy = float(np.mean(diffs)) if diffs else 0.0
    freeze_ratio = float(sum(1 for d in diffs if d < 1.0) / len(diffs)) if diffs else 1.0
    idle_threshold = max(1.0, motion_energy * 0.35)
    idle_ratio = float(sum(1 for d in diffs if d <= idle_threshold) / len(diffs)) if diffs else 1.0
    start_end_diff = float(np.mean(cv2_mod.absdiff(grays[0], grays[-1]))) if len(grays) > 1 else 0.0

    motion_peak_idx = None
    if diffs:
        peak_sample_idx = int(np.argmax(np.array(diffs)))
        motion_peak_idx = peak_sample_idx

    # Longest idle segment
    long_idle_start = None
    long_idle_end = None
    current_start = None
    longest = (0, None, None)
    for i, d in enumerate(diffs):
        if d <= idle_threshold:
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
        long_idle_start = longest[1]
        long_idle_end = longest[2]

    return {
        "path": path,
        "black_frame_ratio": float(black_count / n) if n else 1.0,
        "freeze_ratio": freeze_ratio,
        "blur_score": float(np.mean(blur)) if blur else 0.0,
        "brightness_mean": float(np.mean(brightness)) if brightness else 0.0,
        "motion_energy": motion_energy,
        "start_end_diff": start_end_diff,
        "idle_ratio": idle_ratio,
        "motion_peak_frame_index": motion_peak_idx,
        "long_idle_start_frame_index": long_idle_start,
        "long_idle_end_frame_index": long_idle_end,
    }


def analyze_episode_videos(episode: dict[str, Any], config: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Analyze all videos in an episode.

    If episode has 'segments', plays each segment's videos sequentially
    with simulated playback delay. Otherwise falls back to single-pass analysis.
    """
    features: dict[str, Any] = {}
    errors: list[str] = []
    views = config.get("views", {})

    segments = episode.get("segments")
    if segments:
        # Multi-segment mode: play each segment's videos
        playback_cfg = config.get("playback", {})
        speed = float(playback_cfg.get("speed_multiplier", 8.0))
        sample_every = int(playback_cfg.get("sample_every_n_frames", 3))
        simulate = bool(playback_cfg.get("simulate_delay", True))

        all_segment_features: list[dict[str, Any]] = []
        for seg in segments:
            seg_idx = seg.get("segment_index", len(all_segment_features))
            seg_features: dict[str, Any] = {"segment_index": seg_idx}
            seg_video_paths = seg.get("video_paths", {})
            for view_name, view_cfg in views.items():
                path = seg_video_paths.get(view_name)
                if not path:
                    seg_features[view_name] = {"present": False, "required": bool(view_cfg.get("required"))}
                    if view_cfg.get("required") and view_cfg.get("hard_fail_if_missing", False):
                        errors.append(f"required_view_missing:{view_name}:seg{seg_idx}")
                    continue
                try:
                    vf = play_video(path, speed_multiplier=speed, sample_every_n_frames=sample_every, simulate_delay=simulate)
                    vf["present"] = True
                    vf["required"] = bool(view_cfg.get("required"))
                    seg_features[view_name] = vf
                except Exception as exc:
                    seg_features[view_name] = {
                        "present": True, "required": bool(view_cfg.get("required")),
                        "path": str(path), "error": str(exc),
                    }
                    errors.append(f"video_error:{view_name}:seg{seg_idx}:{exc}")

            # Delay between segments (simulates navigating to next segment)
            seg_delay = float(playback_cfg.get("segment_gap_seconds", 1.0))
            if simulate and seg_delay > 0 and seg_idx < len(segments) - 1:
                import time as _time
                _time.sleep(seg_delay)

            all_segment_features.append(seg_features)

        features["_segmented"] = True
        features["_segments"] = all_segment_features
        # Also aggregate into view-level features for backward compat
        for view_name in views:
            features[view_name] = _aggregate_segment_view(all_segment_features, view_name)
        return features, errors

    # Single-video mode (backward compatible)
    video_paths = episode.get("video_paths") or {}
    playback_cfg = config.get("playback", {})
    use_playback = config.get("playback", {}).get("enabled", True)

    for view_name, view_cfg in views.items():
        path = video_paths.get(view_name)
        if not path:
            features[view_name] = {"present": False, "required": bool(view_cfg.get("required"))}
            if view_cfg.get("required") and view_cfg.get("hard_fail_if_missing", False):
                errors.append(f"required_view_missing:{view_name}")
            continue
        try:
            if use_playback:
                speed = float(playback_cfg.get("speed_multiplier", 8.0))
                sample = int(playback_cfg.get("sample_every_n_frames", 3))
                sim = bool(playback_cfg.get("simulate_delay", True))
                view_features = play_video(path, speed_multiplier=speed, sample_every_n_frames=sample, simulate_delay=sim)
            else:
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


def _aggregate_segment_view(all_segments: list[dict[str, Any]], view_name: str) -> dict[str, Any]:
    """Aggregate per-segment view features into a single view-level summary.

    "Bad is bad" strategy: use MAX for fail-prone features (black, freeze, idle)
    and MIN for quality features (blur, motion, brightness). A single bad segment
    should not be diluted by good ones.
    """
    view_segments = []
    for seg in all_segments:
        vf = seg.get(view_name, {})
        if vf.get("present"):
            view_segments.append(vf)

    if not view_segments:
        return {"present": False, "required": True, "_from_segments": 0}

    agg: dict[str, Any] = {"present": True, "_from_segments": len(view_segments)}

    def _vals(key):
        return [s.get(key, 0.0) for s in view_segments if isinstance(s.get(key), (int, float))]

    # "Bad is bad": worst segment dominates fail-prone features
    agg["black_frame_ratio"] = max(_vals("black_frame_ratio")) if _vals("black_frame_ratio") else 0.0
    agg["freeze_ratio"] = max(_vals("freeze_ratio")) if _vals("freeze_ratio") else 0.0
    agg["idle_ratio"] = max(_vals("idle_ratio")) if _vals("idle_ratio") else 0.0
    # Quality features: worst (lowest) segment
    agg["blur_score"] = min(_vals("blur_score")) if _vals("blur_score") else 0.0
    agg["motion_energy"] = min(_vals("motion_energy")) if _vals("motion_energy") else 0.0
    # Brightness: use min (darkest segment)
    agg["brightness_mean"] = min(_vals("brightness_mean")) if _vals("brightness_mean") else 0.0
    # start_end_diff: use max (biggest change = potential anomaly)
    agg["start_end_diff"] = max(_vals("start_end_diff")) if _vals("start_end_diff") else 0.0

    # Collect ALL timeline data and per-segment anomalies
    all_timelines = []
    all_anomalies = []
    segment_count_with_anomalies = 0
    for s in view_segments:
        tl = s.get("timeline", {})
        seg_anomalies = tl.get("anomaly_intervals", [])
        all_timelines.extend(tl.get("segments", []))
        all_anomalies.extend(seg_anomalies)
        if seg_anomalies:
            segment_count_with_anomalies += 1

    agg["timeline"] = {"segments": all_timelines, "anomaly_intervals": all_anomalies}
    agg["path"] = view_segments[0].get("path", "") if view_segments else ""
    agg["readable"] = True
    agg["frame_count"] = sum(s.get("frame_count", 0) for s in view_segments)
    agg["fps"] = view_segments[0].get("fps", 0) if view_segments else 0
    agg["duration_seconds"] = sum(s.get("duration_seconds", 0) for s in view_segments)
    # Per-segment anomaly ratio
    agg["_segments_with_anomalies"] = segment_count_with_anomalies
    agg["_anomaly_ratio"] = segment_count_with_anomalies / len(view_segments) if view_segments else 0.0

    return agg


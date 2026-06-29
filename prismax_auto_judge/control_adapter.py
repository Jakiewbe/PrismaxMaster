from __future__ import annotations

from pathlib import Path
import re
from urllib.parse import parse_qs, urlparse
from typing import Any, Iterator

from video_features import VIDEO_EXTENSIONS


class PrismaXControlAdapter:
    """Browser control for PrismaX scoring page via Playwright CDP.

    Connects to an already-running Chrome with --remote-debugging-port=9222.
    Fills the React table-based scoring form by clicking dot-span cells.
    """

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self._page = None
        self._browser = None
        self._playwright = None
        self._context = None

    # ── lifecycle ──────────────────────────────────────────────

    def open_page(self) -> None:
        """Connect to Chrome via CDP and navigate to PrismaX dashboard."""
        from playwright.sync_api import sync_playwright  # type: ignore
        import time

        cdp_url = self.config.get("browser", {}).get("cdp_url", "http://127.0.0.1:9222")
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.connect_over_cdp(cdp_url)
        self._context = self._browser.contexts[0]

        # Find existing PrismaX tab or create one
        for pg in self._context.pages:
            if "app.prismax.ai" in pg.url:
                self._page = pg
                break
        if not self._page:
            self._page = self._context.new_page()

        dashboard = self.config.get("browser", {}).get("urls", {}).get("dashboard", "https://app.prismax.ai/")
        self._page.goto(dashboard, timeout=15000, wait_until="domcontentloaded")

        # Verify logged in
        time.sleep(3)
        body = self._page.locator("body").inner_text()
        logged_in_markers = ["All-Time Prisma Points", "Begin Validating", "Control Now", "Review & Earn", "Data Review"]
        if not any(marker in body for marker in logged_in_markers):
            raise RuntimeError("Not logged in to PrismaX - please log in first")

        self._open_review_list()

    def close(self) -> None:
        """Disconnect from browser (does not close Chrome)."""
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()

    # ── page parsing ───────────────────────────────────────────

    def get_current_episode(self) -> dict[str, Any] | None:
        """Parse current scoring page for episode info."""
        if not self._page:
            return None
        url = self._page.url
        url_info = parse_review_url(url)
        body = self._page.locator("body").inner_text()
        episode_id = parse_episode_id(body)
        progress = parse_review_progress(body)
        return {
            "episode_id": episode_id or url_info.get("task_id", "unknown"),
            "task_id": url_info.get("task_id"),
            "upload_id": url_info.get("upload_id"),
            "progress": progress,
            "url": url,
        }

    def get_episode_id(self) -> str | None:
        ep = self.get_current_episode()
        return ep.get("episode_id") if ep else None

    # ── navigation ─────────────────────────────────────────────

    def _open_review_list(self) -> None:
        """Open the current Data Review list from dashboard/banner/carousel UI."""
        import time

        if not self._page:
            raise RuntimeError("Browser page is not open")

        review_list_url = self.config.get("browser", {}).get("urls", {}).get(
            "review_list", "https://app.prismax.ai/data/review"
        )

        if is_review_list_url(self._page.url):
            return

        selectors = self.config.get("browser", {}).get("selectors", {})
        candidate_selectors = selectors.get("validation_entry_buttons") or [
            "button:has-text('Begin Validating')",
            "a:has-text('Begin Validating')",
            "button:has-text('Control Now')",
            "a:has-text('Control Now')",
            "[role='button']:has-text('Begin Validating')",
            "[role='button']:has-text('Control Now')",
        ]

        for _ in range(2):
            for sel in candidate_selectors:
                locator = self._page.locator(sel)
                count = locator.count()
                for idx in range(count):
                    candidate = locator.nth(idx)
                    if not candidate.is_visible():
                        continue
                    candidate.click()
                    time.sleep(4)
                    has_review_button = self._page.locator("button:has-text('Review & Earn')").count() > 0
                    if is_review_list_url(self._page.url) or has_review_button:
                        return

            if self._click_home_slider_next():
                time.sleep(1)
                continue
            break

        self._page.goto(review_list_url, timeout=15000, wait_until="domcontentloaded")
        time.sleep(3)
        if not is_review_list_url(self._page.url):
            raise RuntimeError(f"Could not open PrismaX review list, current url={self._page.url}")

    def _click_home_slider_next(self) -> bool:
        """Advance the home banner/carousel once when the validation entry is hidden on another slide."""
        if not self._page:
            return False
        clicked = self._page.evaluate("""
            () => {
                const isVisible = (el) => {
                    const s = getComputedStyle(el);
                    const r = el.getBoundingClientRect();
                    return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0' && r.width > 0 && r.height > 0;
                };
                const controls = Array.from(document.querySelectorAll('button,[role="button"],a'));
                const next = controls.find((el) => {
                    if (!isVisible(el)) return false;
                    const text = [el.innerText, el.textContent, el.getAttribute('aria-label'), el.getAttribute('title')]
                        .filter(Boolean).join(' ').replace(/\s+/g, ' ').trim().toLowerCase();
                    const cls = String(el.className || '').toLowerCase();
                    return text === 'next' || text.includes('next slide') || cls.includes('swiper-button-next') ||
                        cls.includes('carousel-next') || cls.includes('slick-next');
                });
                if (!next) return false;
                next.click();
                return true;
            }
        """)
        return bool(clicked)

    def open_first_review(self) -> bool:
        """Click first visible Review & Earn button on the review list page."""
        import time

        if not self._page:
            raise RuntimeError("Browser page is not open")

        if not is_review_list_url(self._page.url):
            self._open_review_list()

        clicked = self._page.evaluate("""
            () => {
                const isVisible = (el) => {
                    const s = getComputedStyle(el);
                    const r = el.getBoundingClientRect();
                    return s.display !== 'none' && s.visibility !== 'hidden' && s.opacity !== '0' && r.width > 0 && r.height > 0;
                };
                const buttons = Array.from(document.querySelectorAll('button,[role="button"]'));
                const btn = buttons.find((el) => {
                    if (!isVisible(el)) return false;
                    if (el.disabled || el.getAttribute('aria-disabled') === 'true') return false;
                    const text = [el.innerText, el.textContent, el.getAttribute('aria-label'), el.getAttribute('title')]
                        .filter(Boolean).join(' ').replace(/\s+/g, ' ').trim();
                    return /Review\s*&\s*Earn/i.test(text);
                });
                if (!btn) return false;
                btn.click();
                return true;
            }
        """)
        if not clicked:
            return False
        time.sleep(5)
        return bool(parse_review_url(self._page.url).get("task_id"))

    def next_episode(self) -> None:
        """Click next-episode navigation button."""
        import time
        nav_btns = self._page.locator("[class*='DataQAReview_navBtn']")
        if nav_btns.count() >= 2:
            # Second nav button is usually "next"
            nav_btns.nth(1).click()
            time.sleep(4)
        else:
            raise RuntimeError("next_episode: nav button not found")

    def skip_episode(self, reason: str = "") -> None:
        """Skip current episode (just log reason, move to next)."""
        import logging
        logging.info(f"Skipping episode: {reason}")
        self.next_episode()

    # ── form filling ───────────────────────────────────────────

    def fill_result(self, result: dict[str, Any]) -> None:
        """Fill the scoring form using form_plan. Clicks dot-span cells in React tables."""
        plan = result.get("form_plan", {})
        if not plan.get("can_fill"):
            return

        import time
        click_events = plan.get("click_events", ["mousedown", "mouseup", "click"])

        # Helper JS to click a specific cell
        def click_cell(table_index: int, row: int, col: int) -> str:
            return self._page.evaluate("""
                (args) => {
                    const tables = document.querySelectorAll('table[class*="gridTable"]');
                    if (tables.length <= args.t) return 'no-table';
                    const rows = tables[args.t].querySelectorAll('tbody tr');
                    if (args.r >= rows.length) return 'no-row';
                    const cells = rows[args.r].querySelectorAll('td');
                    if (args.c >= cells.length) return 'no-cell';
                    const td = cells[args.c];
                    const dot = td.querySelector('[class*="dot"]');
                    if (dot) {
                        const events = args.events;
                        events.forEach(type => {
                            dot.dispatchEvent(new MouseEvent(type, {bubbles: true}));
                        });
                        dot.click();
                    }
                    td.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                    td.click();
                    if (dot) {
                        return 'ok dot=' + dot.className.substring(0, 50);
                    }
                    return 'ok no-dot';
                }
            """, {"t": table_index, "r": row, "c": col, "events": click_events})

        # Fill PASS/FAIL (table 0)
        pf_checks = plan.get("pass_fail_checks", {})
        pf_items = list(self.config.get("form", {}).get("pass_fail_items", {}).items())
        for row_idx, (key, item) in enumerate(pf_items):
            check = pf_checks.get(key, {})
            value = check.get("value")
            if value is True:
                col = 1  # Pass
            elif value is False:
                col = 2  # Fail
            else:
                continue
            click_cell(0, row_idx, col)
            time.sleep(0.25)

        # Fill QUALITY (table 1)
        q_sliders = plan.get("quality_sliders", {})
        q_items = list(self.config.get("form", {}).get("quality_sliders", {}).items())
        for row_idx, (key, cfg) in enumerate(q_items):
            slider = q_sliders.get(key, {})
            value = slider.get("value", 3)
            col = max(1, min(5, int(value)))  # 1=Poor ... 5=Exc
            click_cell(1, row_idx, col)
            time.sleep(0.25)

    def submit(self) -> None:
        """Click Submit & earn points button."""
        import time
        sel = self.config.get("browser", {}).get("selectors", {}).get(
            "submit_button", ".DataQAReview_submitBtn__I7VB7"
        )
        btn = self._page.locator(sel).first
        if btn.count() == 0:
            raise RuntimeError("Submit button not found")
        if btn.get_attribute("disabled") is not None:
            raise RuntimeError("Submit button still disabled — form not fully filled")
        btn.first.click()
        time.sleep(3)


    def capture_current_episode_frames(self) -> dict[str, Any]:
        """Capture frames from review-page videos.

        If playback.enabled in live_capture config: plays each video segment
        for >= min_watch_seconds, capturing frames every capture_interval_seconds.
        Otherwise falls back to seek-to-percentage mode.
        """
        import re as _re
        import time

        if not self._page:
            raise RuntimeError("Browser page is not open")

        episode = self.get_current_episode() or {"episode_id": "unknown"}
        episode_id = str(episode.get("episode_id") or "unknown")
        safe_episode_id = _re.sub(r"[^A-Za-z0-9_.-]+", "_", episode_id)
        capture_cfg = self.config.get("live_capture", {})
        view_names = capture_cfg.get("view_names", ["main", "left_wrist", "right_wrist"])
        frame_root = self._resolve_package_path(capture_cfg.get("frame_dir", "data/frames/live")) / safe_episode_id
        frame_root.mkdir(parents=True, exist_ok=True)

        body = self._page.locator("body").inner_text()
        task_prompt = self._extract_task_prompt(body)

        if capture_cfg.get("playback", {}).get("enabled", True):
            return self._capture_with_playback(episode_id, safe_episode_id, task_prompt, frame_root, view_names, capture_cfg)
        return self._capture_with_seek(episode_id, safe_episode_id, task_prompt, frame_root, view_names, capture_cfg)

    # ── playback mode ──────────────────────────────────────────

    def _capture_with_playback(
        self, episode_id: str, safe_id: str, task_prompt: str,
        frame_root, view_names: list[str], capture_cfg: dict[str, Any],
    ) -> dict[str, Any]:
        """Real playback: play each video segment, capture frames during playback."""
        import time

        pb_cfg = capture_cfg.get("playback", {})
        min_watch = float(pb_cfg.get("min_watch_seconds", 30))
        capture_interval = float(pb_cfg.get("capture_interval_seconds", 4))
        speed = float(pb_cfg.get("speed_multiplier", 10))
        max_segments = int(pb_cfg.get("max_segments", 20))

        # Detect segment count from page (progress text like "1 of 14")
        body = self._page.locator("body").inner_text()
        segments_total = self._detect_segment_count(body)

        frame_paths: dict[str, list[str]] = {}
        video_sources: dict[str, str] = {}
        errors: list[str] = []
        total_watch_seconds = 0.0
        segments_seen = 0

        for seg_idx in range(max_segments):
            if seg_idx > 0:
                # Navigate to next segment
                navs = self._page.locator("[class*='DataQAReview_navBtn']")
                if navs.count() >= 2:
                    try:
                        navs.nth(1).click()
                        time.sleep(2)
                    except Exception:
                        break
                else:
                    break

            # Ensure videos play
            self._page.evaluate("""() => {
                document.querySelectorAll('video').forEach(v => {
                    v.muted = true; v.currentTime = 0;
                    v.play().catch(() => {});
                });
            }""")
            time.sleep(1.5)

            # Wait for at least one video ready
            for _ in range(15):
                ready = self._page.evaluate("""() => {
                    for (const v of document.querySelectorAll('video'))
                        if (v.readyState >= 2 && v.videoWidth > 0 && !v.paused) return true;
                    return false;
                }""")
                if ready:
                    break
                time.sleep(0.5)

            seg_start = time.monotonic()
            seg_frames: dict[str, list[str]] = {}
            seg_watch = 0.0

            # Capture frames during playback
            while seg_watch < min_watch:
                # Check if video ended
                all_ended = self._page.evaluate("""() => {
                    const vs = document.querySelectorAll('video');
                    if (vs.length === 0) return true;
                    return Array.from(vs).every(v => v.ended || v.currentTime >= v.duration - 0.5);
                }""")
                if all_ended:
                    break

                # Check if videos froze (no progress in 5 seconds)
                progress_made = self._page.evaluate("""() => {
                    for (const v of document.querySelectorAll('video'))
                        if (v.readyState >= 2 && !v.paused && !v.ended && v.currentTime > 0.1) return true;
                    return false;
                }""")
                if not progress_made:
                    # Try replay
                    self._page.evaluate("""() => {
                        document.querySelectorAll('video').forEach(v => {
                            v.currentTime = 0; v.play().catch(() => {});
                        });
                    }""")
                    time.sleep(1)
                    seg_watch += 1  # count attempted time

                # Screenshot each visible video
                timestamp = int(seg_watch)
                for vi, view in enumerate(view_names):
                    try:
                        els = self._page.locator("video")
                        if vi >= els.count():
                            break
                        box = els.nth(vi).bounding_box()
                        if not box or box["width"] < 10:
                            continue
                        out = frame_root / f"{view}_seg{seg_idx+1:02d}_t{timestamp:03d}s.jpg"
                        self._page.screenshot(
                            path=str(out),
                            clip={"x": box["x"], "y": box["y"], "width": box["width"], "height": box["height"]},
                            type="jpeg", quality=80, timeout=5000,
                        )
                        nonblack = self._image_nonblack_ratio(out)
                        if nonblack < 0.15:
                            try: out.unlink()
                            except OSError: pass
                            continue
                        seg_frames.setdefault(view, []).append(str(out))
                        if not video_sources.get(view):
                            src = self._page.evaluate(f"""() => {{
                                const v = document.querySelectorAll('video')[{vi}];
                                return (v.src || '').substring(0, 200);
                            }}""")
                            video_sources[view] = str(src or "")
                    except Exception as exc:
                        errors.append(f"{view}:seg{seg_idx+1}:t{timestamp}:{type(exc).__name__}")

                sleep_time = capture_interval / speed
                time.sleep(max(0.05, sleep_time))
                seg_watch += capture_interval

            elapsed = time.monotonic() - seg_start
            total_watch_seconds += seg_watch
            segments_seen += 1

            # Merge segment frames
            for view, paths in seg_frames.items():
                frame_paths.setdefault(view, []).extend(paths)

            if seg_watch >= min_watch:
                break  # watched enough

        if not any(frame_paths.values()):
            raise RuntimeError("No review video frames captured; playback produced no usable frames")

        return {
            "episode_id": episode_id,
            "task_prompt": task_prompt,
            "video_paths": {},
            "frame_paths": frame_paths,
            "video_sources": video_sources,
            "metadata": {
                "source": "prismax_live_page",
                "url": self._page.url,
                "capture_method": "playback",
                "capture_errors": errors,
                "watch_seconds": round(total_watch_seconds, 1),
                "segments_total": segments_total,
                "segments_seen": segments_seen,
                "all_segments_seen": segments_seen >= segments_total if segments_total > 0 else False,
            },
        }

    @staticmethod
    def _detect_segment_count(body: str) -> int:
        import re
        m = re.search(r"(\d+)\s+of\s+(\d+)", body)
        return int(m.group(2)) if m else 1

    # ── legacy seek mode ───────────────────────────────────────

    def _capture_with_seek(
        self, episode_id: str, safe_id: str, task_prompt: str,
        frame_root, view_names: list[str], capture_cfg: dict[str, Any],
    ) -> dict[str, Any]:
        """Legacy: seek to percentage points and screenshot."""
        import time

        points = capture_cfg.get("percent_points", [0, 10, 25, 50, 75, 90, 100])
        wait_seconds = float(capture_cfg.get("wait_until_ready_seconds", 8))
        warmup_seconds = float(capture_cfg.get("warmup_play_seconds", 1.0))
        min_nonblack_ratio = float(capture_cfg.get("min_nonblack_ratio", 0.70))
        video_count = int(self._page.evaluate("""
            () => Array.from(document.querySelectorAll('video')).filter(v => {
                const rect = v.getBoundingClientRect();
                const style = getComputedStyle(v);
                return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
            }).length
        """))

        frame_paths: dict[str, list[str]] = {}
        video_sources: dict[str, str] = {}
        errors: list[str] = []
        for idx in range(video_count):
            view = view_names[idx] if idx < len(view_names) else f"view_{idx}"
            frame_paths[view] = []
            for pct in points:
                try:
                    meta = self._seek_video_and_get_clip(idx, float(pct), wait_seconds, warmup_seconds)
                    video_sources[view] = str(meta.get("src") or "")
                    clip = meta.get("clip") or {}
                    if not meta.get("ok"):
                        errors.append(f"{view}:{pct}:{meta.get('error', 'seek_failed')}")
                        continue
                    out = frame_root / f"{view}_{int(pct):03d}.jpg"
                    self._page.screenshot(
                        path=str(out),
                        clip={"x": max(0, float(clip.get("x", 0))),
                              "y": max(0, float(clip.get("y", 0))),
                              "width": max(1, float(clip.get("width", 1))),
                              "height": max(1, float(clip.get("height", 1)))},
                        type="jpeg", quality=88, timeout=5000,
                    )
                    nonblack = self._image_nonblack_ratio(out)
                    if nonblack < min_nonblack_ratio:
                        errors.append(f"{view}:{pct}:black_or_not_ready:{nonblack:.2f}")
                        try: out.unlink()
                        except OSError: pass
                        continue
                    frame_paths[view].append(str(out))
                except Exception as exc:
                    errors.append(f"{view}:{pct}:{type(exc).__name__}:{exc}")

        if not any(frame_paths.values()):
            raise RuntimeError("No review video frames captured; page screenshot fallback failed")

        return {
            "episode_id": episode_id,
            "task_prompt": task_prompt,
            "video_paths": {},
            "frame_paths": frame_paths,
            "video_sources": video_sources,
            "metadata": {
                "source": "prismax_live_page",
                "url": self._page.url,
                "capture_method": "page_screenshot_clip",
                "capture_errors": errors,
                "capture_config": {
                    "percent_points": points,
                    "wait_until_ready_seconds": wait_seconds,
                    "warmup_play_seconds": warmup_seconds,
                    "min_nonblack_ratio": min_nonblack_ratio,
                },
                "captured_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "progress": episode.get("progress"),
                "task_id": episode.get("task_id"),
                "upload_id": episode.get("upload_id"),
            },
        }

    def _seek_video_and_get_clip(self, index: int, percent: float, wait_seconds: float, warmup_seconds: float) -> dict[str, Any]:
        if not self._page:
            raise RuntimeError("Browser page is not open")
        return self._page.evaluate(
            """
            async ({index, percent, waitSeconds, warmupSeconds}) => {
                const sleep = (ms) => new Promise(r => setTimeout(r, ms));
                const visible = (v) => {
                    const rect = v.getBoundingClientRect();
                    const style = getComputedStyle(v);
                    return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
                };
                const videos = Array.from(document.querySelectorAll('video')).filter(visible);
                const v = videos[index];
                if (!v) return {ok: false, error: 'video_not_found'};
                try { v.scrollIntoView({block: 'center', inline: 'center'}); } catch (e) {}
                const deadline = Date.now() + waitSeconds * 1000;
                while (Date.now() < deadline) {
                    if (visible(v) && v.videoWidth > 0 && v.videoHeight > 0 && Number.isFinite(v.duration) && v.duration > 0) break;
                    try { v.load && v.load(); } catch (e) {}
                    await sleep(250);
                }
                if (!(v.videoWidth > 0 && v.videoHeight > 0)) return {ok: false, error: 'video_not_ready'};
                try {
                    v.muted = true;
                    await v.play().catch(() => null);
                    await sleep(Math.max(0, warmupSeconds) * 1000);
                    v.pause();
                } catch (e) {}
                const duration = Number.isFinite(v.duration) && v.duration > 0 ? v.duration : 0;
                if (duration > 0) {
                    const target = Math.max(0.05, Math.min(duration - 0.05, duration * percent / 100));
                    await new Promise((resolve, reject) => {
                        let settled = false;
                        const done = () => { if (!settled) { settled = true; cleanup(); resolve(); } };
                        const fail = () => { if (!settled) { settled = true; cleanup(); reject(new Error('seek failed')); } };
                        const cleanup = () => {
                            v.removeEventListener('seeked', done);
                            v.removeEventListener('error', fail);
                        };
                        v.addEventListener('seeked', done, {once: true});
                        v.addEventListener('error', fail, {once: true});
                        try { v.currentTime = target; } catch (err) { fail(); }
                        setTimeout(done, 1800);
                    });
                    await sleep(200);
                }
                try { v.scrollIntoView({block: 'center', inline: 'center'}); } catch (e) {}
                await sleep(100);
                const rect = v.getBoundingClientRect();
                return {
                    ok: true,
                    src: v.currentSrc || v.src || '',
                    duration,
                    clip: {
                        x: rect.left + window.scrollX,
                        y: rect.top + window.scrollY,
                        width: rect.width,
                        height: rect.height,
                    },
                };
            }
            """,
            {"index": index, "percent": percent, "waitSeconds": wait_seconds, "warmupSeconds": warmup_seconds},
        )

    def _image_nonblack_ratio(self, path: Path) -> float:
        try:
            import cv2  # type: ignore
            img = cv2.imread(str(path))
            if img is None or img.size == 0:
                return 0.0
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            return float((gray > 12).sum()) / float(gray.size)
        except Exception:
            return 1.0

    def return_to_arm_queue(self, arm_label: str | None = None) -> bool:
        """Navigate back to robots-center, select target arm, and join its queue."""
        import time

        if not self._page:
            raise RuntimeError("Browser page is not open")
        post_cfg = self.config.get("post_vla", {})
        target = arm_label or post_cfg.get("target_arm_label") or "Arena Arm"
        url = post_cfg.get("robot_center_url") or self.config.get("browser", {}).get("urls", {}).get(
            "robot_center", "https://app.prismax.ai/robots-center"
        )
        attempts = int(post_cfg.get("max_return_attempts", 3))
        self._page.goto(url, timeout=15000, wait_until="domcontentloaded")
        time.sleep(3)
        for _ in range(max(1, attempts)):
            clicked = self._page.evaluate(
                """
                ({target}) => {
                    const visible = (el) => {
                        const style = getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
                    };
                    const norm = (s) => String(s || '').replace(/\s+/g, ' ').trim();
                    const nodes = Array.from(document.querySelectorAll('button,[role="button"],a,div,section,article'));
                    const labelNode = nodes.find(el => visible(el) && norm(el.innerText || el.textContent).includes(target));
                    if (!labelNode) return {ok: false, reason: 'arm_not_found'};
                    const card = labelNode.closest('[class*="robotCard"], [class*="card"], article, section') || labelNode;
                    try { card.scrollIntoView({block: 'center', inline: 'center'}); } catch (e) {}
                    try { card.click(); } catch (e) {}
                    const controls = Array.from((card || document).querySelectorAll('button,[role="button"],a'));
                    let join = controls.find(el => {
                        if (!visible(el)) return false;
                        if (el.disabled || el.getAttribute('aria-disabled') === 'true') return false;
                        const text = norm([el.innerText, el.textContent, el.getAttribute('aria-label'), el.getAttribute('title')].filter(Boolean).join(' ')).toLowerCase();
                        return /join|enter|start|begin|queue|control|入队|进入/.test(text) && !/leave/.test(text);
                    });
                    if (!join) {
                        join = Array.from(document.querySelectorAll('button,[role="button"],a')).find(el => {
                            if (!visible(el)) return false;
                            if (el.disabled || el.getAttribute('aria-disabled') === 'true') return false;
                            const text = norm([el.innerText, el.textContent, el.getAttribute('aria-label'), el.getAttribute('title')].filter(Boolean).join(' ')).toLowerCase();
                            return /enter live control|join queue|enter pool|control now/.test(text) && !/leave/.test(text);
                        });
                    }
                    if (!join) return {ok: false, reason: 'join_button_not_found'};
                    try { join.scrollIntoView({block: 'center', inline: 'center'}); } catch (e) {}
                    join.click();
                    return {ok: true, reason: 'clicked_join', target};
                }
                """,
                {"target": target},
            )
            if clicked and clicked.get("ok"):
                time.sleep(3)
                return True
            time.sleep(2)
        return False

    def _extract_task_prompt(self, body_text: str) -> str:
        lines = [line.strip() for line in body_text.splitlines() if line.strip()]
        for idx, line in enumerate(lines):
            lower = line.lower()
            if any(key in lower for key in ["instruction", "task prompt", "task", "prompt"]):
                if idx + 1 < len(lines):
                    return lines[idx + 1][:500]
                return line[:500]
        return ""

    def _resolve_package_path(self, value: str | Path) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return Path(__file__).resolve().parent / path

    def abort_submit(self, reason: str) -> None:
        raise RuntimeError(f"submit_aborted:{reason}")


def parse_review_url(url: str) -> dict[str, str | None]:
    parsed = urlparse(url)
    upload_id = parse_qs(parsed.query).get("upload", [None])[0]
    task_id = None
    match = re.search(r"/data/review/([^/?#]+)", parsed.path)
    if match:
        task_id = match.group(1)
    return {"task_id": task_id, "upload_id": upload_id}


def is_review_list_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.netloc == "app.prismax.ai" and parsed.path.rstrip("/") == "/data/review"


def parse_episode_id(page_text: str, pattern: str = r"Episode #(\d+)") -> str | None:
    match = re.search(pattern, page_text)
    return match.group(1) if match else None


def parse_review_progress(page_text: str, pattern: str = r"(\d+) of (\d+)") -> dict[str, int] | None:
    match = re.search(pattern, page_text)
    if not match:
        return None
    return {"current": int(match.group(1)), "total": int(match.group(2))}


def iter_local_episodes(video_dir: str | Path) -> Iterator[dict[str, Any]]:
    """Iterate episodes from local video files.

    Supports two naming conventions:
      Single-segment:  {episode_id}_{view}.mp4
      Multi-segment:   {episode_id}_seg{NN}_{view}.mp4

    Returns episodes with optional 'segments' list for multi-segment videos.
    """
    import re as _re

    root = Path(video_dir)
    if not root.exists():
        return

    # Regex: capture episode_id, optional segment number, and view
    seg_pattern = _re.compile(
        r"^(.+?)(?:_seg(\d+))?_(main|left_wrist|right_wrist)\.(?:mp4|mov|mkv|webm|avi)$",
        _re.IGNORECASE,
    )

    # Group by (episode_id, segment_index)
    grouped: dict[tuple[str, str | None], dict[str, str]] = {}
    for path in sorted(root.iterdir()):
        if not path.is_file() or path.suffix.lower() not in VIDEO_EXTENSIONS:
            continue
        match = seg_pattern.match(path.name)
        if match:
            ep_id = match.group(1)
            seg_idx = match.group(2)  # None for single-segment
            view = match.group(3)
            grouped.setdefault((ep_id, seg_idx), {})[view] = str(path)
        else:
            # Fallback: treat stem as episode_id, detect view from suffix
            stem = path.stem
            ep_id = stem
            view = "main"
            for suffix, view_name in [("_main", "main"), ("_left_wrist", "left_wrist"), ("_right_wrist", "right_wrist")]:
                if stem.endswith(suffix):
                    ep_id = stem[: -len(suffix)]
                    view = view_name
                    break
            grouped.setdefault((ep_id, None), {})[view] = str(path)

    # Group segments by episode_id
    episodes: dict[str, list[dict[str, Any]]] = {}
    for (ep_id, seg_idx), paths in grouped.items():
        seg = {"video_paths": paths}
        if seg_idx is not None:
            seg["segment_index"] = int(seg_idx)
        episodes.setdefault(ep_id, []).append(seg)

    for ep_id, seg_list in episodes.items():
        # Sort segments by index
        seg_list.sort(key=lambda s: s.get("segment_index", 0))
        # Assign sequential indices if not present
        for i, seg in enumerate(seg_list):
            if "segment_index" not in seg:
                seg["segment_index"] = i + 1

        if len(seg_list) > 1:
            # Multi-segment episode
            yield {
                "episode_id": ep_id,
                "task_prompt": "",
                "video_paths": seg_list[0]["video_paths"],  # backward compat
                "segments": seg_list,
                "metadata": {"source": "local_folder", "segment_count": len(seg_list)},
            }
        else:
            # Single-segment episode
            yield {
                "episode_id": ep_id,
                "task_prompt": "",
                "video_paths": seg_list[0]["video_paths"],
                "metadata": {"source": "local_folder"},
            }

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
        import time
        time.sleep(3)
        body = self._page.locator("body").inner_text()
        if "All-Time Prisma Points" not in body and "Begin Validating" not in body:
            raise RuntimeError("Not logged in to PrismaX — please log in first")

        # Navigate to review list
        selectors = self.config.get("browser", {}).get("selectors", {})
        begin_sel = selectors.get("begin_validating_button", "button:has-text('Begin Validating')")
        self._page.locator(begin_sel).first.click()
        time.sleep(4)

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

    def open_first_review(self) -> bool:
        """Click first Review & Earn button on the review list page."""
        sel = self.config.get("browser", {}).get("selectors", {}).get(
            "review_earn_button", "button:has-text('Review & Earn')"
        )
        import time
        btn = self._page.locator(sel).first
        if btn.count() == 0:
            return False
        btn.first.click()
        time.sleep(5)
        return True

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

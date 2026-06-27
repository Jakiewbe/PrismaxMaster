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
        logged_in_markers = ["All-Time Prisma Points", "Begin Validating", "Control Now", "Review & Earn"]
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

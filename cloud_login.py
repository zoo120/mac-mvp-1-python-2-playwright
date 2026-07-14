"""Keep a cloud-side Xianyu browser session alive for QR/manual login."""

from __future__ import annotations

import argparse
import asyncio
import time
from pathlib import Path

from crawler import (
    PROFILE_DIR,
    build_search_url,
    needs_manual_intervention,
)
from runtime_config import browser_args, browser_headless


async def run_cloud_login_session(
    screenshot_path: str | Path,
    *,
    wait_seconds: int = 180,
    keyword: str = "床垫",
) -> None:
    """Open Xianyu in the server browser profile and refresh a screenshot while waiting."""
    from playwright.async_api import async_playwright

    target = Path(screenshot_path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=browser_headless(),
            args=browser_args(),
            no_viewport=True,
            locale="zh-CN",
        )
        context.set_default_timeout(8_000)
        page = context.pages[0] if context.pages else await context.new_page()
        try:
            await page.goto(build_search_url(keyword), wait_until="domcontentloaded", timeout=60_000)
            end_at = time.monotonic() + max(30, int(wait_seconds))
            while time.monotonic() < end_at:
                try:
                    # Some pages hide the QR/login panel until a login entry is clicked.
                    for text in ("立即登录", "登录", "扫码登录"):
                        locator = page.get_by_text(text, exact=False).first
                        if await locator.count():
                            await locator.click(timeout=1_000)
                            break
                except Exception:
                    pass
                try:
                    await page.screenshot(path=str(target), full_page=True)
                except Exception:
                    pass
                try:
                    body_text = await page.locator("body").inner_text(timeout=2_000)
                    if not needs_manual_intervention(body_text) and "扫码登录" not in body_text:
                        await page.wait_for_timeout(3_000)
                except Exception:
                    pass
                await page.wait_for_timeout(3_000)
        finally:
            await context.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Start a cloud-side Xianyu login session.")
    parser.add_argument("--screenshot", required=True)
    parser.add_argument("--wait", type=int, default=180)
    parser.add_argument("--keyword", default="床垫")
    args = parser.parse_args()
    asyncio.run(
        run_cloud_login_session(
            args.screenshot,
            wait_seconds=args.wait,
            keyword=args.keyword,
        )
    )


if __name__ == "__main__":
    main()

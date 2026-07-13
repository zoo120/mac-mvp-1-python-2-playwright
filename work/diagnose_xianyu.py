import asyncio
import json
from pathlib import Path

from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / ".playwright-profile"
SCREENSHOT = ROOT / "work" / "xianyu-diagnostic.png"
URL = "https://www.goofish.com/search?q=%E9%81%AE%E9%98%B3%E6%A3%9A"


async def main() -> None:
    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE),
            headless=False,
            no_viewport=True,
            locale="zh-CN",
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
        await page.wait_for_timeout(5_000)
        print("URL:", page.url)
        print("TITLE:", await page.title())
        body_text = await page.locator("body").inner_text(timeout=10_000)
        print("BODY_START:")
        print(body_text[:5_000])
        print("BODY_END")
        selectors = [
            "a",
            "a[href]",
            "a[href*='item']",
            "[class*='item']",
            "[class*='card']",
            "[class*='feed']",
        ]
        for selector in selectors:
            print("COUNT", selector, await page.locator(selector).count())
        links = await page.locator("a[href]").evaluate_all(
            """
            nodes => nodes.slice(0, 100).map(node => ({
              href: node.getAttribute('href') || '',
              text: (node.innerText || '').trim().slice(0, 200),
              className: typeof node.className === 'string' ? node.className : ''
            }))
            """
        )
        print("LINKS:")
        print(json.dumps(links, ensure_ascii=False, indent=2))
        await page.screenshot(path=str(SCREENSHOT), full_page=True)
        print("SCREENSHOT:", SCREENSHOT)
        await context.close()


if __name__ == "__main__":
    asyncio.run(main())


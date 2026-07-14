"""Playwright crawler and resilient field parsers for Xianyu search cards."""

from __future__ import annotations

import argparse
import asyncio
import logging
import random
import re
import sys
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any
from urllib.parse import quote_plus, urljoin

from database import (
    DEFAULT_DB_PATH,
    get_connection,
    get_enabled_keywords,
    init_database,
    upsert_candidate,
    upsert_crawled_item,
)
from rules import evaluate_item
from runtime_config import PROJECT_DIR, browser_args, browser_headless, env_path


GOOFISH_ORIGIN = "https://www.goofish.com"
SEARCH_URL = f"{GOOFISH_ORIGIN}/search?q={{keyword}}"
PROFILE_DIR = env_path("XIANYU_PROFILE_DIR", PROJECT_DIR / ".playwright-profile")
LOG_DIR = env_path("XIANYU_LOG_DIR", PROJECT_DIR / "logs")
LOGGER = logging.getLogger("xianyu_crawler")
MIN_KEYWORD_DELAY_SECONDS = 10
MAX_KEYWORD_DELAY_SECONDS = 30
MIN_LOADED_CARD_COUNT = 5
MANUAL_INTERVENTION_POLL_TIMEOUT_SECONDS = 120
MANUAL_INTERVENTION_POLL_INTERVAL_MS = 3_000

CARD_SELECTORS = (
    "a[href*='item?id=']",
    "a[href*='/item?']",
    "a[href*='/item/']",
    "[data-testid*='item'] a[href]",
)
MANUAL_INTERVENTION_PHRASES = (
    "请登录",
    "登录后继续",
    "登录后可以",
    "立即登录",
    "扫码登录",
    "安全验证",
    "输入验证码",
    "滑动验证",
)
PROVINCE_LABELS = (
    "北京",
    "天津",
    "上海",
    "重庆",
    "河北",
    "山西",
    "辽宁",
    "吉林",
    "黑龙江",
    "江苏",
    "浙江",
    "安徽",
    "福建",
    "江西",
    "山东",
    "河南",
    "湖北",
    "湖南",
    "广东",
    "海南",
    "四川",
    "贵州",
    "云南",
    "陕西",
    "甘肃",
    "青海",
    "台湾",
    "内蒙古",
    "广西",
    "西藏",
    "宁夏",
    "新疆",
    "香港",
    "澳门",
    "海外",
)

PRICE_RE = re.compile(
    r"(?:¥|￥|价格\s*[:：]?)\s*([0-9][0-9,]*(?:\.[0-9]+)?)",
    re.IGNORECASE,
)
WANT_RE = re.compile(
    r"([0-9]+(?:\.[0-9]+)?)\s*(万)?\s*(?:人)?\s*(?:想要|想买)",
    re.IGNORECASE,
)


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def parse_price(text: Any, *, allow_plain: bool = False) -> float | None:
    """Extract the first explicit price, returning None when unavailable."""
    cleaned = _clean_text(text)
    match = PRICE_RE.search(cleaned)
    if not match and allow_plain:
        match = re.fullmatch(r"([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:元)?", cleaned)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", ""))
    except ValueError:
        return None


def parse_want_count(text: Any, *, allow_plain: bool = False) -> int | None:
    """Extract Xianyu's want count, including values expressed in 万."""
    cleaned = _clean_text(text)
    match = WANT_RE.search(cleaned)
    plain_match = None
    if not match and allow_plain:
        plain_match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*(万)?", cleaned)
        match = plain_match
    if not match:
        return None
    try:
        value = float(match.group(1))
    except ValueError:
        return None
    if match.group(2):
        value *= 10_000
    return int(value)


def parse_location(text: Any) -> str:
    """Extract the province label shown near the end of a search card."""
    tail = _clean_text(text)[-50:]
    matches = [
        (tail.rfind(province), province)
        for province in PROVINCE_LABELS
        if province in tail
    ]
    if not matches:
        return ""
    return max(matches, key=lambda match: match[0])[1]


def absolute_item_url(url: Any) -> str:
    value = _clean_text(url)
    if not value:
        return ""
    return urljoin(f"{GOOFISH_ORIGIN}/", value)


def absolute_image_url(url: Any) -> str:
    value = _clean_text(url)
    if not value:
        return ""
    if value.startswith("//"):
        return f"https:{value}"
    return urljoin(f"{GOOFISH_ORIGIN}/", value)


def build_search_url(keyword: str) -> str:
    return SEARCH_URL.format(keyword=quote_plus(keyword))


def parse_limit(value: str) -> int:
    try:
        limit = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--limit 必须是 1 到 20 的整数") from exc
    if not 1 <= limit <= 20:
        raise argparse.ArgumentTypeError("--limit 必须在 1 到 20 之间")
    return limit


def needs_manual_intervention(page_text: Any) -> bool:
    text = _clean_text(page_text)
    return any(phrase in text for phrase in MANUAL_INTERVENTION_PHRASES)


def should_wait_for_manual_intervention(page_text: Any, card_count: int) -> bool:
    """Pause only when login/verification text appears and results are absent."""
    return (
        needs_manual_intervention(page_text)
        and card_count < MIN_LOADED_CARD_COUNT
    )


def _fallback_title(raw_text: str) -> str:
    if not raw_text:
        return ""
    candidate = re.split(
        r"\s*(?:¥|￥|价格\s*[:：]?|[0-9]+(?:\.[0-9]+)?\s*万?\s*(?:人)?想要)",
        raw_text,
        maxsplit=1,
    )[0]
    return _clean_text(candidate)


def normalize_card(
    raw: Mapping[str, Any],
    keyword: str,
    crawl_date: str,
) -> dict[str, Any]:
    """Normalize a browser-extracted card without assuming every field exists."""
    raw_text = _clean_text(raw.get("text"))
    title = _clean_text(raw.get("title")) or _fallback_title(raw_text)
    structured_price = parse_price(raw.get("price"), allow_plain=True)
    structured_wants = parse_want_count(raw.get("want_count"), allow_plain=True)

    return {
        "keyword": _clean_text(keyword),
        "title": title,
        "price": structured_price if structured_price is not None else parse_price(raw_text),
        "want_count": (
            structured_wants
            if structured_wants is not None
            else parse_want_count(raw_text)
        ),
        "location": _clean_text(raw.get("location")) or parse_location(raw_text),
        "seller_type": _clean_text(raw.get("seller_type")),
        "item_url": absolute_item_url(raw.get("href")),
        "image_url": absolute_image_url(raw.get("image")),
        "raw_text": raw_text,
        "crawl_date": crawl_date,
    }


def save_keyword_batch(
    keyword: str,
    items: list[Mapping[str, Any]],
    db_path: str | Path = DEFAULT_DB_PATH,
) -> tuple[int, int]:
    """Save one keyword as a single transaction and refresh its candidates."""
    saved_items = 0
    saved_candidates = 0
    with get_connection(db_path) as connection:
        for item in items:
            upsert_crawled_item(item, db_path, connection=connection)
            saved_items += 1

            decision = evaluate_item(item)
            upsert_candidate(
                {
                    "product_name": decision.product_name,
                    "keyword": keyword,
                    "title": _clean_text(item.get("title")),
                    "price": item.get("price"),
                    "want_count": item.get("want_count"),
                    "item_url": _clean_text(item.get("item_url")),
                    "reason": decision.reason,
                    "risk_level": decision.risk_level,
                    "recommendation_status": decision.recommendation_status,
                },
                db_path,
                connection=connection,
            )
            saved_candidates += 1
    return saved_items, saved_candidates


def configure_logging() -> None:
    """Log to both the terminal and a persistent local file."""
    if LOGGER.handlers:
        return
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    LOGGER.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    file_handler = logging.FileHandler(LOG_DIR / "crawler.log", encoding="utf-8")
    file_handler.setFormatter(formatter)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    LOGGER.addHandler(file_handler)
    LOGGER.addHandler(stream_handler)


async def _body_text(page: Any) -> str:
    try:
        return await page.locator("body").inner_text(timeout=5_000)
    except Exception as exc:
        LOGGER.debug("读取页面正文失败：%s", exc)
        return ""


async def _wait_for_manual_intervention(
    page: Any,
    keyword: str,
    *,
    mode: str = "prompt",
) -> None:
    page_text = await _body_text(page)
    card_locator = await _find_card_locator(page)
    card_count = await card_locator.count() if card_locator is not None else 0
    if not should_wait_for_manual_intervention(page_text, card_count):
        return

    LOGGER.warning("关键词“%s”的页面需要登录或人工验证。", keyword)
    if mode == "poll":
        attempts = max(
            1,
            MANUAL_INTERVENTION_POLL_TIMEOUT_SECONDS
            * 1000
            // MANUAL_INTERVENTION_POLL_INTERVAL_MS,
        )
        for _ in range(attempts):
            await page.wait_for_timeout(MANUAL_INTERVENTION_POLL_INTERVAL_MS)
            page_text = await _body_text(page)
            card_locator = await _find_card_locator(page)
            card_count = await card_locator.count() if card_locator is not None else 0
            if not should_wait_for_manual_intervention(page_text, card_count):
                LOGGER.info("关键词“%s”的登录/验证已完成，继续采集。", keyword)
                return
        raise RuntimeError(
            "闲鱼要求登录或安全验证。请在弹出的浏览器里完成登录/验证后，再点一次搜索。"
        )

    prompt = (
        "请在浏览器中完成登录/验证，完成后回到这里按回车继续。"
        "若暂时无法完成，也可直接按回车尝试继续："
    )
    try:
        await asyncio.to_thread(input, prompt)
    except EOFError:
        LOGGER.warning("当前终端无法读取输入，将继续尝试采集。")
    await page.wait_for_timeout(1_000)


async def _find_card_locator(page: Any) -> Any | None:
    for selector in CARD_SELECTORS:
        try:
            locator = page.locator(selector)
            if await locator.count() > 0:
                return locator
        except Exception as exc:
            LOGGER.debug("商品选择器失败 %s：%s", selector, exc)
    return None


async def _extract_card_payload(card: Any) -> dict[str, str]:
    return await card.evaluate(
        """
        element => {
          const anchor = element.matches('a') ? element : element.querySelector('a[href]');
          let container = element;
          let current = element;
          for (let i = 0; i < 4 && current.parentElement; i += 1) {
            const parent = current.parentElement;
            const parentText = (parent.innerText || '').trim();
            if (parentText.length > 0 && parentText.length <= 1200) container = parent;
            current = parent;
          }
          const pickText = selectors => {
            for (const selector of selectors) {
              const node = container.querySelector(selector);
              const value = node && (node.getAttribute('title') || node.innerText || node.textContent);
              if (value && value.trim()) return value.trim();
            }
            return '';
          };
          const image = container.querySelector('img');
          const text = (container.innerText || element.innerText || '').trim();
          let sellerType = pickText(["[class*='seller-type']", "[class*='sellerType']"]);
          if (!sellerType) {
            for (const candidate of ['商家', '个人卖家', '企业卖家']) {
              if (text.includes(candidate)) { sellerType = candidate; break; }
            }
          }
          return {
            title: pickText(['[title]', 'h3', 'h2', "[class*='title']", "[class*='name']"]),
            text,
            href: anchor ? (anchor.getAttribute('href') || anchor.href || '') : '',
            image: image ? (image.currentSrc || image.src || image.getAttribute('data-src') || '') : '',
            price: pickText(["[class*='price']", "[class*='Price']"]),
            want_count: pickText(["[class*='want']", "[class*='Want']", "[class*='heat']"]),
            location: pickText(["[class*='location']", "[class*='area']", "[class*='region']"]),
            seller_type: sellerType,
          };
        }
        """
    )


async def crawl_keyword(
    page: Any,
    keyword: str,
    limit: int = 20,
    *,
    manual_intervention_mode: str = "prompt",
) -> list[dict[str, Any]]:
    """Open one search page and return up to ``limit`` normalized cards."""
    if not 1 <= limit <= 20:
        raise ValueError("limit 必须在 1 到 20 之间")

    url = build_search_url(keyword)
    LOGGER.info("开始采集关键词“%s”：%s", keyword, url)
    await page.goto(url, wait_until="domcontentloaded", timeout=60_000)
    await page.wait_for_timeout(3_000)
    await _wait_for_manual_intervention(
        page,
        keyword,
        mode=manual_intervention_mode,
    )

    for _ in range(3):
        locator = await _find_card_locator(page)
        if locator is not None and await locator.count() >= limit:
            break
        await page.evaluate("window.scrollBy(0, Math.max(window.innerHeight, 700))")
        await page.wait_for_timeout(1_200)

    locator = await _find_card_locator(page)
    if locator is None:
        page_text = await _body_text(page)
        if needs_manual_intervention(page_text):
            raise RuntimeError(
                "闲鱼要求登录或安全验证。管理员请先在后台“云端登录”页面扫码/验证；"
                "如果仍然受限，请让学员用商品链接直接保存素材。"
            )
        LOGGER.warning("关键词“%s”未找到商品卡片，页面结构可能已变化。", keyword)
        return []

    crawl_date = date.today().isoformat()
    results: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    card_count = min(await locator.count(), max(limit * 3, limit))
    for index in range(card_count):
        if len(results) >= limit:
            break
        try:
            payload = await _extract_card_payload(locator.nth(index))
            item = normalize_card(payload, keyword, crawl_date)
            if not item["title"] and not item["raw_text"]:
                continue
            item_url = item["item_url"]
            if item_url and item_url in seen_urls:
                continue
            if item_url:
                seen_urls.add(item_url)
            results.append(item)
        except Exception as exc:
            LOGGER.exception("关键词“%s”第 %s 个商品解析失败：%s", keyword, index + 1, exc)

    LOGGER.info("关键词“%s”解析到 %s 条商品。", keyword, len(results))
    if not results:
        page_text = await _body_text(page)
        if needs_manual_intervention(page_text):
            raise RuntimeError(
                "闲鱼要求登录或安全验证。管理员请先在后台“云端登录”页面扫码/验证；"
                "如果仍然受限，请让学员用商品链接直接保存素材。"
            )
    return results


def _keyword_rows(
    db_path: str | Path,
    keyword: str | None,
) -> list[Mapping[str, Any]]:
    if keyword is None:
        return get_enabled_keywords(db_path)
    with get_connection(db_path) as connection:
        row = connection.execute(
            "SELECT id, keyword, category, enabled, priority, note FROM keywords WHERE keyword = ?",
            (keyword,),
        ).fetchone()
    if row is None:
        raise ValueError(f"关键词未在数据库中：{keyword}。请先运行 init_db.py。")
    return [row]


async def crawl_keyword_sequence(
    page: Any,
    keyword_rows: list[Mapping[str, Any]],
    limit: int,
    db_path: str | Path,
    *,
    crawl_func: Any = None,
    save_func: Any = None,
    sleep_func: Any = None,
    delay_func: Any = None,
) -> None:
    """Crawl rows sequentially, isolating each keyword failure."""
    crawl_func = crawl_func or crawl_keyword
    save_func = save_func or save_keyword_batch
    sleep_func = sleep_func or asyncio.sleep
    delay_func = delay_func or random.uniform

    for index, row in enumerate(keyword_rows):
        current_keyword = str(row["keyword"])
        try:
            items = await crawl_func(page, current_keyword, limit)
            item_count, candidate_count = save_func(
                current_keyword, items, db_path
            )
            LOGGER.info(
                "关键词“%s”已保存 %s 条采集记录和 %s 条候选判断。",
                current_keyword,
                item_count,
                candidate_count,
            )
        except Exception as exc:
            LOGGER.exception("关键词“%s”采集失败，继续下一个：%s", current_keyword, exc)

        if index < len(keyword_rows) - 1:
            wait_seconds = delay_func(
                MIN_KEYWORD_DELAY_SECONDS,
                MAX_KEYWORD_DELAY_SECONDS,
            )
            LOGGER.info("为避免高频请求，等待 %.1f 秒。", wait_seconds)
            await sleep_func(wait_seconds)


async def crawl_student_keyword_once(
    page: Any,
    keyword: str,
    limit: int,
    db_path: str | Path,
    *,
    crawl_func: Any = None,
    save_func: Any = None,
) -> tuple[int, int]:
    """Crawl one arbitrary learner keyword and save results without requiring setup."""
    crawl_func = crawl_func or crawl_keyword
    save_func = save_func or save_keyword_batch
    current_keyword = _clean_text(keyword)
    if not current_keyword:
        raise ValueError("请输入要搜索的商品关键词")
    items = await crawl_func(
        page,
        current_keyword,
        limit,
        manual_intervention_mode="poll",
    )
    return save_func(current_keyword, items, db_path)


async def run_student_keyword_crawler(
    keyword: str,
    limit: int = 20,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> tuple[int, int]:
    """Run a visible one-keyword crawl for the learner-facing assistant page."""
    if not 1 <= limit <= 20:
        raise ValueError("limit 必须在 1 到 20 之间")
    configure_logging()
    init_database(db_path)

    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright 尚未安装。请先运行 pip install -r requirements.txt，"
            "再运行 playwright install chromium。"
        ) from exc

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=browser_headless(),
            args=browser_args(),
            no_viewport=True,
            locale="zh-CN",
        )
        context.set_default_timeout(10_000)
        page = context.pages[0] if context.pages else await context.new_page()
        try:
            return await crawl_student_keyword_once(page, keyword, limit, db_path)
        finally:
            await context.close()


def run_student_keyword_search(
    keyword: str,
    limit: int = 20,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> tuple[int, int]:
    """Synchronous wrapper used by Streamlit learner mode."""
    return asyncio.run(run_student_keyword_crawler(keyword, limit, db_path))


async def run_crawler(
    keyword: str | None = None,
    limit: int = 20,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> None:
    """Run the visible, sequential, rate-limited browser crawl."""
    if not 1 <= limit <= 20:
        raise ValueError("limit 必须在 1 到 20 之间")
    configure_logging()
    init_database(db_path)
    keywords = _keyword_rows(db_path, keyword)
    if not keywords:
        LOGGER.warning("没有已启用的关键词，采集结束。")
        return

    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright 尚未安装。请先运行 pip install -r requirements.txt，"
            "再运行 playwright install chromium。"
        ) from exc

    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=browser_headless(),
            args=browser_args(),
            no_viewport=True,
            locale="zh-CN",
        )
        context.set_default_timeout(10_000)
        page = context.pages[0] if context.pages else await context.new_page()
        try:
            await crawl_keyword_sequence(page, keywords, limit, db_path)
        finally:
            await context.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="闲鱼热卖品监测 MVP 采集器")
    parser.add_argument(
        "--keyword",
        help="只采集一个已初始化的关键词；不传则采集全部已启用关键词",
    )
    parser.add_argument(
        "--student-keyword",
        help="学员选品助手使用：采集一个任意关键词，不要求预先加入关键词库",
    )
    parser.add_argument(
        "--limit",
        type=parse_limit,
        default=20,
        help="每个关键词抓取条数，范围 1-20（默认：20）",
    )
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"SQLite 数据库路径（默认：{DEFAULT_DB_PATH.name}）",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        if args.student_keyword:
            item_count, candidate_count = asyncio.run(
                run_student_keyword_crawler(args.student_keyword, args.limit, args.db)
            )
            print(
                f"学员关键词“{args.student_keyword}”已采集 {item_count} 条，"
                f"生成 {candidate_count} 条初筛结果。"
            )
        else:
            asyncio.run(run_crawler(args.keyword, args.limit, args.db))
    except KeyboardInterrupt:
        print("\n已由用户停止采集。")
        return 130
    except Exception as exc:
        configure_logging()
        LOGGER.exception("采集器无法启动：%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

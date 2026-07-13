"""Save Xianyu detail-page copywriting and images as local material packages."""

from __future__ import annotations

import asyncio
import argparse
import json
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from crawler import PROFILE_DIR, absolute_image_url
from database import DEFAULT_DB_PATH, init_database, record_saved_asset
from runtime_config import PROJECT_DIR, browser_args, browser_headless, env_path


SAVED_PRODUCTS_DIR = env_path("XIANYU_SAVED_PRODUCTS_DIR", PROJECT_DIR / "saved_products")
LOGGER = logging.getLogger("xianyu_asset_saver")
MAX_IMAGES_PER_PRODUCT = 12
BAD_TITLES = {"为你推荐", "搜索", "闲鱼", "Goofish", "商品详情"}
COPY_END_MARKERS = (
    " 展开 聊一聊",
    " 聊一聊 立即购买",
    " 立即购买 收藏",
    " 为你推荐 ",
    " 发闲置 ",
    " 消息 商品码",
    " 阿里巴巴集团",
)
COPY_START_PATTERNS = (
    r"描述不符包邮退\s*满足条件时，买家可退货且运费由卖家承担\s*",
    r"[0-9]+(?:\.[0-9]+)?\s*(?:万)?浏览\s*",
    r"[0-9]+(?:\.[0-9]+)?\s*(?:万)?人想要\s*",
)


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def extract_detail_copy(text: Any) -> str:
    """Extract the seller-written detail copy from noisy Xianyu page text."""
    cleaned = _clean_text(text)
    if not cleaned:
        return ""

    for marker in COPY_END_MARKERS:
        marker_index = cleaned.find(marker)
        if marker_index >= 0:
            cleaned = cleaned[:marker_index].strip()
            break

    best_start = -1
    for pattern in COPY_START_PATTERNS:
        matches = list(re.finditer(pattern, cleaned))
        if matches:
            best_start = max(best_start, matches[-1].end())
    if best_start >= 0:
        cleaned = cleaned[best_start:].strip()

    cleaned = re.sub(
        r"^(搜索\s+)?网页版发闲置功能又升级啦！\s*",
        "",
        cleaned,
    ).strip()
    cleaned = re.sub(
        r"^.*?(?:担保交易\s+举报|闲鱼号\s+担保交易\s+举报)\s*",
        "",
        cleaned,
    ).strip()
    cleaned = re.sub(r"^¥\s*[0-9.,\s-]+(?:包邮)?\s*", "", cleaned).strip()
    return cleaned


def _is_usable_detail_copy(text: str) -> bool:
    if not _clean_text(text):
        return False
    guarantee_only_phrases = (
        "满足条件时，买家可退货且运费由卖家承担",
        "描述不符包邮退",
    )
    return not any(phrase in text for phrase in guarantee_only_phrases)


def safe_folder_name(value: str, fallback: str = "商品素材") -> str:
    """Return a short macOS-safe folder name."""
    cleaned = _clean_text(value)
    cleaned = re.sub(r"[\\/:*?\"<>|]+", "_", cleaned)
    cleaned = re.sub(r"\s+", "_", cleaned).strip("._ ")
    cleaned = re.sub(r"_+", "_", cleaned)
    return (cleaned or fallback)[:80]


def validate_item_url(url: str) -> str:
    """Allow Xianyu detail URLs and reject unrelated or malformed URLs."""
    value = _clean_text(url)
    parsed = urlparse(value)
    host = parsed.netloc.lower()
    if parsed.scheme not in {"http", "https"} or not host:
        raise ValueError("商品链接不是有效网址")
    if host.endswith("goofish.com"):
        return value
    if host == "market.m.taobao.com" and "idleFish" in parsed.path:
        return value
    raise ValueError("只支持闲鱼商品链接")


def filter_image_urls(urls: list[str]) -> list[str]:
    """Normalize and deduplicate likely product image URLs."""
    result: list[str] = []
    seen: set[str] = set()
    for url in urls:
        normalized = absolute_image_url(url)
        if not normalized:
            continue
        lowered = normalized.lower()
        if lowered.startswith("data:") or lowered.endswith(".svg"):
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
        if len(result) >= MAX_IMAGES_PER_PRODUCT:
            break
    return result


def normalize_detail_payload(
    raw: dict[str, Any],
    item_url: str,
    title_hint: str = "",
) -> dict[str, Any]:
    """Normalize browser-extracted detail fields without requiring every field."""
    page_title = _clean_text(raw.get("title"))
    hinted_title = _clean_text(title_hint)
    title = (
        hinted_title
        if not page_title or page_title in BAD_TITLES
        else page_title
    ) or "商品素材"
    raw_text = _clean_text(raw.get("raw_text"))
    page_description = extract_detail_copy(raw.get("description"))
    raw_description = extract_detail_copy(raw_text)
    description = (
        page_description
        if _is_usable_detail_copy(page_description)
        else raw_description or page_description
    )
    return {
        "title": title,
        "description": description,
        "item_url": validate_item_url(item_url),
        "images": filter_image_urls(list(raw.get("images") or [])),
        "raw_text": raw_text,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
    }


def _unique_folder(root: Path, folder_name: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = root / f"{folder_name}_{timestamp}"
    if not base.exists():
        return base
    for index in range(2, 100):
        candidate = root / f"{folder_name}_{timestamp}_{index}"
        if not candidate.exists():
            return candidate
    return root / f"{folder_name}_{timestamp}_{datetime.now().microsecond}"


def save_material_files(
    payload: dict[str, Any],
    image_files: list[tuple[str, bytes, str]],
    output_root: str | Path = SAVED_PRODUCTS_DIR,
) -> dict[str, Any]:
    """Write copy, metadata, and downloaded images into a local folder."""
    root = Path(output_root).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    folder = _unique_folder(root, safe_folder_name(str(payload.get("title") or "")))
    image_dir = folder / "images"
    image_dir.mkdir(parents=True, exist_ok=True)

    copy_text = _clean_text(payload.get("description") or payload.get("raw_text"))
    (folder / "文案.txt").write_text(f"{copy_text}\n", encoding="utf-8")
    (folder / "商品信息.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    saved_images: list[str] = []
    for index, (_source_url, content, ext) in enumerate(image_files, start=1):
        suffix = re.sub(r"[^a-zA-Z0-9]", "", ext or "jpg").lower() or "jpg"
        image_path = image_dir / f"图片{index}.{suffix}"
        image_path.write_bytes(content)
        saved_images.append(str(image_path))

    return {
        "folder_path": folder,
        "copy_path": folder / "文案.txt",
        "metadata_path": folder / "商品信息.json",
        "image_count": len(saved_images),
        "image_paths": saved_images,
    }


def _extension_from_content_type(content_type: str, url: str) -> str:
    lowered = content_type.lower()
    if "png" in lowered:
        return "png"
    if "webp" in lowered:
        return "webp"
    if "gif" in lowered:
        return "gif"
    path = urlparse(url).path.lower()
    for ext in ("jpg", "jpeg", "png", "webp", "gif"):
        if path.endswith(f".{ext}"):
            return "jpg" if ext == "jpeg" else ext
    return "jpg"


async def _download_images(context: Any, urls: list[str]) -> list[tuple[str, bytes, str]]:
    image_files: list[tuple[str, bytes, str]] = []
    for url in urls[:MAX_IMAGES_PER_PRODUCT]:
        try:
            response = await context.request.get(url, timeout=15_000)
            if not response.ok:
                LOGGER.warning("图片下载失败 %s：HTTP %s", url, response.status)
                continue
            content = await response.body()
            if not content:
                continue
            ext = _extension_from_content_type(
                response.headers.get("content-type", ""),
                url,
            )
            image_files.append((url, content, ext))
        except Exception as exc:
            LOGGER.warning("图片下载失败 %s：%s", url, exc)
    return image_files


async def _extract_detail_payload(page: Any) -> dict[str, Any]:
    return await page.evaluate(
        """
        () => {
          const textOf = selector => {
            const node = document.querySelector(selector);
            return node ? (node.getAttribute('content') || node.innerText || node.textContent || '').trim() : '';
          };
          const title =
            textOf('meta[property="og:title"]') ||
            textOf('h1') ||
            textOf('[class*="title"]') ||
            document.title ||
            '';
          const description =
            textOf('meta[property="og:description"]') ||
            textOf('[class*="desc"]') ||
            textOf('[class*="Desc"]') ||
            textOf('[class*="content"]') ||
            '';
          const images = [];
          const ogImage = textOf('meta[property="og:image"]');
          if (ogImage) images.push(ogImage);
          for (const img of Array.from(document.images || [])) {
            const src = img.currentSrc || img.src || img.getAttribute('data-src') || img.getAttribute('data-lazy-src') || '';
            const width = img.naturalWidth || img.width || 0;
            const height = img.naturalHeight || img.height || 0;
            if (src && Math.max(width, height) >= 160) images.push(src);
          }
          return {
            title,
            description,
            images,
            raw_text: (document.body && document.body.innerText || '').trim(),
          };
        }
        """
    )


async def capture_product_assets(
    item_url: str,
    title_hint: str = "",
    db_path: str | Path = DEFAULT_DB_PATH,
    output_root: str | Path = SAVED_PRODUCTS_DIR,
) -> dict[str, Any]:
    """Open one product detail page, save copy/images, and record the package."""
    validated_url = validate_item_url(item_url)
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright 尚未安装，无法保存商品素材。") from exc

    init_database(db_path)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=browser_headless(),
            args=browser_args(),
            no_viewport=True,
            locale="zh-CN",
        )
        context.set_default_timeout(12_000)
        page = context.pages[0] if context.pages else await context.new_page()
        try:
            await page.goto(validated_url, wait_until="domcontentloaded", timeout=60_000)
            await page.wait_for_timeout(3_000)
            raw_payload = await _extract_detail_payload(page)
            payload = normalize_detail_payload(raw_payload, validated_url, title_hint)
            image_files = await _download_images(context, payload["images"])
            result = save_material_files(payload, image_files, output_root)
            record_saved_asset(
                {
                    "item_url": payload["item_url"],
                    "title": payload["title"],
                    "copy_text": payload["description"],
                    "folder_path": str(result["folder_path"]),
                    "image_count": result["image_count"],
                    "source": "streamlit",
                },
                db_path,
            )
            return {**payload, **result}
        finally:
            await context.close()


def save_product_assets(
    item_url: str,
    title_hint: str = "",
    db_path: str | Path = DEFAULT_DB_PATH,
    output_root: str | Path = SAVED_PRODUCTS_DIR,
) -> dict[str, Any]:
    """Synchronous wrapper used by Streamlit buttons."""
    return asyncio.run(capture_product_assets(item_url, title_hint, db_path, output_root))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="保存闲鱼商品详情页文案和图片")
    parser.add_argument("--item-url", required=True, help="闲鱼商品链接")
    parser.add_argument("--title-hint", default="", help="列表页标题，用于详情页标题抓取失败时兜底")
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB_PATH,
        help=f"SQLite 数据库路径（默认：{DEFAULT_DB_PATH.name}）",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=SAVED_PRODUCTS_DIR,
        help=f"素材保存目录（默认：{SAVED_PRODUCTS_DIR.name}）",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        result = save_product_assets(
            args.item_url,
            title_hint=args.title_hint,
            db_path=args.db,
            output_root=args.output_root,
        )
        print(f"已保存到：{result['folder_path']}，图片 {result['image_count']} 张。")
    except KeyboardInterrupt:
        print("\n已由用户停止保存。")
        return 130
    except Exception as exc:
        print(f"保存失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

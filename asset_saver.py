"""Save Xianyu detail-page copywriting and images as local material packages."""

from __future__ import annotations

import asyncio
import argparse
import json
import logging
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from crawler import PROFILE_DIR, absolute_image_url
from database import DEFAULT_DB_PATH, init_database, record_saved_asset
from rules import FILTER_TERMS, WEIGHT_TERMS, evaluate_item
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


def _extract_price_from_text(text: str) -> float | None:
    match = re.search(r"[¥￥]\s*([0-9]+(?:\.[0-9]+)?)", str(text or ""))
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _extract_want_count_from_text(text: str) -> int | None:
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)(万)?\s*人?想要", str(text or ""))
    if not match:
        return None
    number = float(match.group(1))
    if match.group(2):
        number *= 10_000
    return int(number)


def _matched_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    lowered = str(text or "").lower()
    result: list[str] = []
    for term in terms:
        normalized = term.lower()
        if normalized == "包":
            if re.search(r"(女包|男包|包包|手提包|背包|挎包|包袋)", lowered):
                result.append(term)
            continue
        if normalized in lowered:
            result.append(term)
    return result


def _bullet_lines(values: list[str], fallback: str = "暂无明显提取项") -> str:
    if not values:
        return f"- {fallback}"
    return "\n".join(f"- {value}" for value in values)


def _extract_selling_points(title: str, description: str) -> list[str]:
    text = _clean_text(f"{title} {description}")
    parts = re.split(r"[。！？!?；;，,\n]+", text)
    result: list[str] = []
    seen: set[str] = set()
    for part in parts:
        cleaned = _clean_text(part)
        if len(cleaned) < 4 or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned[:80])
        if len(result) >= 6:
            break
    return result


def build_delivery_report(payload: dict[str, Any], image_count: int) -> str:
    """Create a learner-facing product handoff report for the saved package."""
    title = _clean_text(payload.get("title")) or "商品素材"
    description = _clean_text(payload.get("description") or payload.get("raw_text"))
    raw_text = _clean_text(payload.get("raw_text"))
    combined_text = _clean_text(f"{title} {description} {raw_text}")
    price = _extract_price_from_text(combined_text)
    want_count = _extract_want_count_from_text(combined_text)
    decision = evaluate_item(
        {
            "title": title,
            "price": price,
            "want_count": want_count,
            "item_url": payload.get("item_url"),
        }
    )
    weight_terms = _matched_terms(combined_text, WEIGHT_TERMS)
    filter_terms = _matched_terms(combined_text, FILTER_TERMS)
    selling_points = _extract_selling_points(title, description)

    risk_notes: list[str] = []
    if filter_terms:
        risk_notes.append(f"命中过滤词：{'、'.join(filter_terms)}，不建议直接交付。")
    if image_count <= 0:
        risk_notes.append("没有成功保存图片，需要重新保存或人工补图。")
    if want_count is None:
        risk_notes.append("未识别到想要数，热度只能人工二次判断。")
    if price is not None and price <= 30:
        risk_notes.append("价格偏低，可能是配件、小百货或引流低价。")
    if not risk_notes:
        risk_notes.append("未发现明显硬伤，但仍需确认供货、物流、售后和同款价格。")

    price_text = f"¥{price:g}" if price is not None else "未识别"
    want_text = str(want_count) if want_count is not None else "未识别"
    weighted_text = "、".join(weight_terms) if weight_terms else "未命中"
    filtered_text = "、".join(filter_terms) if filter_terms else "未命中"

    return f"""# 选品交付建议

## 商品基础信息

- 商品标题：{title}
- 商品链接：{payload.get("item_url", "")}
- 识别价格：{price_text}
- 识别想要数：{want_text}
- 已保存图片：{image_count} 张

## 系统初步判断

- 推荐状态：{decision.recommendation_status}
- 风险等级：{decision.risk_level}
- 判断原因：{decision.reason}
- 加权词：{weighted_text}
- 过滤词：{filtered_text}

## 可用于上架的卖点

{_bullet_lines(selling_points)}

## 交付前必须检查

- 闲鱼/淘宝/拼多多同款价格是否还有利润空间。
- 商品是否能稳定发货，是否适合发物流或快递。
- 大件商品要先确认运费、退换货责任、安装/尺寸问题。
- 文案和图片可参考，不要原封不动照搬，避免重复和侵权风险。

## 风险提醒

{_bullet_lines(risk_notes)}

## 素材包里有什么

- `文案.txt`：从商品页提取的主要文案。
- `images/`：保存到的商品图片。
- `商品信息.json`：原始结构化信息，方便后续排查。
- `选品交付建议.md`：本文件，可直接发给学员做判断参考。
"""


def create_material_zip(folder: Path) -> Path:
    """Zip the saved product folder so learners can download one file."""
    zip_path = folder / "素材包.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(folder.rglob("*")):
            if path == zip_path or path.is_dir():
                continue
            archive.write(path, path.relative_to(folder))
    return zip_path


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

    report_path = folder / "选品交付建议.md"
    report_path.write_text(
        build_delivery_report(payload, len(saved_images)),
        encoding="utf-8",
    )
    zip_path = create_material_zip(folder)

    return {
        "folder_path": folder,
        "copy_path": folder / "文案.txt",
        "metadata_path": folder / "商品信息.json",
        "report_path": report_path,
        "zip_path": zip_path,
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
        print(
            f"已保存到：{result['folder_path']}，图片 {result['image_count']} 张，"
            f"素材包：{result['zip_path']}。"
        )
    except KeyboardInterrupt:
        print("\n已由用户停止保存。")
        return 130
    except Exception as exc:
        print(f"保存失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

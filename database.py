"""SQLite persistence for the local Xianyu monitoring MVP."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from runtime_config import PROJECT_DIR, env_path


DEFAULT_DB_PATH = env_path("XIANYU_DB_PATH", PROJECT_DIR / "xianyu_monitor.db")

BUILTIN_KEYWORDS: tuple[tuple[str, str, int, str], ...] = (
    ("遮阳棚", "遮阳户外", 100, "首批内置关键词"),
    ("雨棚", "遮阳户外", 90, "首批内置关键词"),
    ("伸缩遮阳棚", "遮阳户外", 100, "首批内置关键词"),
    ("烧烤炉", "餐饮设备", 100, "首批内置关键词"),
    ("烤串炉", "餐饮设备", 100, "首批内置关键词"),
    ("摆摊车", "餐饮设备", 100, "首批内置关键词"),
    ("小吃车", "餐饮设备", 100, "首批内置关键词"),
    ("冷饮桶", "餐饮设备", 90, "首批内置关键词"),
    ("果汁鼎", "餐饮设备", 90, "首批内置关键词"),
    ("制冰机", "餐饮设备", 100, "首批内置关键词"),
    ("儿童学习桌", "学习家具", 90, "首批内置关键词"),
    ("升降学习桌", "学习家具", 90, "首批内置关键词"),
    ("篮球架", "体育器材", 90, "首批内置关键词"),
    ("乒乓球桌", "体育器材", 90, "首批内置关键词"),
    ("空气循环扇", "通风制冷", 90, "首批内置关键词"),
    ("工业风扇", "通风制冷", 100, "首批内置关键词"),
    ("冷风机", "通风制冷", 100, "首批内置关键词"),
    ("移动空调", "通风制冷", 100, "首批内置关键词"),
    ("操作台", "商用厨房", 90, "首批内置关键词"),
    ("发酵箱", "商用厨房", 90, "首批内置关键词"),
    ("醒发箱", "商用厨房", 90, "首批内置关键词"),
    ("猫别墅", "宠物设备", 90, "首批内置关键词"),
    ("狗笼", "宠物设备", 90, "首批内置关键词"),
    ("宠物烘干箱", "宠物设备", 100, "首批内置关键词"),
    ("粉碎机", "农业机械", 100, "首批内置关键词"),
    ("铡草机", "农业机械", 100, "首批内置关键词"),
    ("脱粒机", "农业机械", 100, "首批内置关键词"),
    ("大棚膜", "农业用品", 90, "首批内置关键词"),
    ("不锈钢橱柜", "商用厨房", 90, "首批内置关键词"),
    ("升降桌", "家具", 90, "首批内置关键词"),
)


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS keywords (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        keyword TEXT NOT NULL UNIQUE,
        category TEXT NOT NULL DEFAULT '',
        enabled INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
        priority INTEGER NOT NULL DEFAULT 0,
        note TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS crawled_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        keyword TEXT NOT NULL,
        title TEXT NOT NULL DEFAULT '',
        price REAL,
        want_count INTEGER,
        location TEXT NOT NULL DEFAULT '',
        seller_type TEXT NOT NULL DEFAULT '',
        item_url TEXT NOT NULL DEFAULT '',
        image_url TEXT NOT NULL DEFAULT '',
        raw_text TEXT NOT NULL DEFAULT '',
        crawl_date TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS product_candidates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_name TEXT NOT NULL DEFAULT '',
        keyword TEXT NOT NULL,
        title TEXT NOT NULL DEFAULT '',
        price REAL,
        want_count INTEGER,
        item_url TEXT NOT NULL DEFAULT '',
        reason TEXT NOT NULL DEFAULT '',
        risk_level TEXT NOT NULL DEFAULT '',
        recommendation_status TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS saved_product_assets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        item_url TEXT NOT NULL DEFAULT '',
        title TEXT NOT NULL DEFAULT '',
        copy_text TEXT NOT NULL DEFAULT '',
        folder_path TEXT NOT NULL DEFAULT '',
        image_count INTEGER NOT NULL DEFAULT 0,
        source TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_crawled_daily_link
    ON crawled_items(keyword, item_url, crawl_date)
    WHERE item_url <> ''
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_candidate_keyword_link
    ON product_candidates(keyword, item_url)
    WHERE item_url <> ''
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_saved_asset_link
    ON saved_product_assets(item_url)
    WHERE item_url <> ''
    """,
    "CREATE INDEX IF NOT EXISTS idx_keywords_enabled_priority ON keywords(enabled, priority DESC)",
    "CREATE INDEX IF NOT EXISTS idx_crawled_date_keyword ON crawled_items(crawl_date, keyword)",
    "CREATE INDEX IF NOT EXISTS idx_crawled_price_want ON crawled_items(price, want_count)",
    "CREATE INDEX IF NOT EXISTS idx_candidates_status ON product_candidates(recommendation_status, risk_level)",
    "CREATE INDEX IF NOT EXISTS idx_saved_assets_updated ON saved_product_assets(updated_at DESC)",
)


def get_connection(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Return a configured SQLite connection."""
    path = Path(db_path).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 30000")
    return connection


def init_database(db_path: str | Path = DEFAULT_DB_PATH) -> None:
    """Create all tables/indexes and insert the built-in keywords once."""
    with get_connection(db_path) as connection:
        for statement in SCHEMA_STATEMENTS:
            connection.execute(statement)
        connection.executemany(
            """
            INSERT INTO keywords(keyword, category, enabled, priority, note)
            VALUES (?, ?, 1, ?, ?)
            ON CONFLICT(keyword) DO NOTHING
            """,
            BUILTIN_KEYWORDS,
        )


def get_enabled_keywords(
    db_path: str | Path = DEFAULT_DB_PATH,
) -> list[sqlite3.Row]:
    """Return enabled keywords in crawl order."""
    with get_connection(db_path) as connection:
        return connection.execute(
            """
            SELECT id, keyword, category, enabled, priority, note
            FROM keywords
            WHERE enabled = 1
            ORDER BY priority DESC, id ASC
            """
        ).fetchall()


def set_keyword_enabled(
    keyword_id: int,
    enabled: bool,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> None:
    """Enable or disable one keyword."""
    with get_connection(db_path) as connection:
        cursor = connection.execute(
            """
            UPDATE keywords
            SET enabled = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (int(enabled), int(keyword_id)),
        )
        if cursor.rowcount != 1:
            raise ValueError(f"关键词 ID 不存在: {keyword_id}")


def _connection_for_write(
    db_path: str | Path,
    connection: sqlite3.Connection | None,
) -> tuple[sqlite3.Connection, bool]:
    if connection is not None:
        return connection, False
    return get_connection(db_path), True


def upsert_crawled_item(
    item: Mapping[str, Any],
    db_path: str | Path = DEFAULT_DB_PATH,
    *,
    connection: sqlite3.Connection | None = None,
) -> int:
    """Insert a crawl snapshot, updating the same linked item on the same day."""
    conn, owns_connection = _connection_for_write(db_path, connection)
    try:
        if item.get("item_url"):
            conn.execute(
                """
                INSERT INTO crawled_items(
                    keyword, title, price, want_count, location, seller_type,
                    item_url, image_url, raw_text, crawl_date
                ) VALUES(
                    :keyword, :title, :price, :want_count, :location, :seller_type,
                    :item_url, :image_url, :raw_text, :crawl_date
                )
                ON CONFLICT(keyword, item_url, crawl_date) WHERE item_url <> ''
                DO UPDATE SET
                    title = excluded.title,
                    price = excluded.price,
                    want_count = excluded.want_count,
                    location = excluded.location,
                    seller_type = excluded.seller_type,
                    image_url = excluded.image_url,
                    raw_text = excluded.raw_text
                """,
                dict(item),
            )
            row = conn.execute(
                """
                SELECT id FROM crawled_items
                WHERE keyword = ? AND item_url = ? AND crawl_date = ?
                """,
                (item["keyword"], item["item_url"], item["crawl_date"]),
            ).fetchone()
            item_id = int(row[0])
        else:
            cursor = conn.execute(
                """
                INSERT INTO crawled_items(
                    keyword, title, price, want_count, location, seller_type,
                    item_url, image_url, raw_text, crawl_date
                ) VALUES(
                    :keyword, :title, :price, :want_count, :location, :seller_type,
                    :item_url, :image_url, :raw_text, :crawl_date
                )
                """,
                dict(item),
            )
            item_id = int(cursor.lastrowid)
        if owns_connection:
            conn.commit()
        return item_id
    except Exception:
        if owns_connection:
            conn.rollback()
        raise
    finally:
        if owns_connection:
            conn.close()


def upsert_candidate(
    candidate: Mapping[str, Any],
    db_path: str | Path = DEFAULT_DB_PATH,
    *,
    connection: sqlite3.Connection | None = None,
) -> int:
    """Insert or refresh the current candidate judgement for a linked item."""
    conn, owns_connection = _connection_for_write(db_path, connection)
    try:
        if candidate.get("item_url"):
            conn.execute(
                """
                INSERT INTO product_candidates(
                    product_name, keyword, title, price, want_count, item_url,
                    reason, risk_level, recommendation_status
                ) VALUES(
                    :product_name, :keyword, :title, :price, :want_count, :item_url,
                    :reason, :risk_level, :recommendation_status
                )
                ON CONFLICT(keyword, item_url) WHERE item_url <> ''
                DO UPDATE SET
                    product_name = excluded.product_name,
                    title = excluded.title,
                    price = excluded.price,
                    want_count = excluded.want_count,
                    reason = excluded.reason,
                    risk_level = excluded.risk_level,
                    recommendation_status = excluded.recommendation_status,
                    created_at = CURRENT_TIMESTAMP
                """,
                dict(candidate),
            )
            row = conn.execute(
                "SELECT id FROM product_candidates WHERE keyword = ? AND item_url = ?",
                (candidate["keyword"], candidate["item_url"]),
            ).fetchone()
            candidate_id = int(row[0])
        else:
            cursor = conn.execute(
                """
                INSERT INTO product_candidates(
                    product_name, keyword, title, price, want_count, item_url,
                    reason, risk_level, recommendation_status
                ) VALUES(
                    :product_name, :keyword, :title, :price, :want_count, :item_url,
                    :reason, :risk_level, :recommendation_status
                )
                """,
                dict(candidate),
            )
            candidate_id = int(cursor.lastrowid)
        if owns_connection:
            conn.commit()
        return candidate_id
    except Exception:
        if owns_connection:
            conn.rollback()
        raise
    finally:
        if owns_connection:
            conn.close()


def record_saved_asset(
    asset: Mapping[str, Any],
    db_path: str | Path = DEFAULT_DB_PATH,
    *,
    connection: sqlite3.Connection | None = None,
) -> int:
    """Insert or refresh a locally saved product material package."""
    conn, owns_connection = _connection_for_write(db_path, connection)
    try:
        if asset.get("item_url"):
            conn.execute(
                """
                INSERT INTO saved_product_assets(
                    item_url, title, copy_text, folder_path, image_count, source
                ) VALUES(
                    :item_url, :title, :copy_text, :folder_path, :image_count, :source
                )
                ON CONFLICT(item_url) WHERE item_url <> ''
                DO UPDATE SET
                    title = excluded.title,
                    copy_text = excluded.copy_text,
                    folder_path = excluded.folder_path,
                    image_count = excluded.image_count,
                    source = excluded.source,
                    updated_at = CURRENT_TIMESTAMP
                """,
                {
                    "item_url": str(asset.get("item_url") or ""),
                    "title": str(asset.get("title") or ""),
                    "copy_text": str(asset.get("copy_text") or ""),
                    "folder_path": str(asset.get("folder_path") or ""),
                    "image_count": int(asset.get("image_count") or 0),
                    "source": str(asset.get("source") or ""),
                },
            )
            row = conn.execute(
                "SELECT id FROM saved_product_assets WHERE item_url = ?",
                (str(asset.get("item_url") or ""),),
            ).fetchone()
            asset_id = int(row[0])
        else:
            cursor = conn.execute(
                """
                INSERT INTO saved_product_assets(
                    item_url, title, copy_text, folder_path, image_count, source
                ) VALUES(
                    :item_url, :title, :copy_text, :folder_path, :image_count, :source
                )
                """,
                {
                    "item_url": "",
                    "title": str(asset.get("title") or ""),
                    "copy_text": str(asset.get("copy_text") or ""),
                    "folder_path": str(asset.get("folder_path") or ""),
                    "image_count": int(asset.get("image_count") or 0),
                    "source": str(asset.get("source") or ""),
                },
            )
            asset_id = int(cursor.lastrowid)
        if owns_connection:
            conn.commit()
        return asset_id
    except Exception:
        if owns_connection:
            conn.rollback()
        raise
    finally:
        if owns_connection:
            conn.close()


def list_saved_assets(
    db_path: str | Path = DEFAULT_DB_PATH,
    *,
    limit: int = 200,
) -> list[sqlite3.Row]:
    """Return recently saved product material packages."""
    with get_connection(db_path) as connection:
        return connection.execute(
            """
            SELECT id, item_url, title, copy_text, folder_path, image_count,
                   source, created_at, updated_at
            FROM saved_product_assets
            ORDER BY updated_at DESC, id DESC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        ).fetchall()

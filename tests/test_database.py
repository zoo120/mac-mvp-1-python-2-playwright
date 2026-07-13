from datetime import date

from database import (
    BUILTIN_KEYWORDS,
    get_connection,
    init_database,
    list_saved_assets,
    record_saved_asset,
    set_keyword_enabled,
    upsert_crawled_item,
)
from crawler import save_keyword_batch


def test_init_is_idempotent_and_seeds_all_keywords(tmp_path):
    db_path = tmp_path / "test.db"

    init_database(db_path)
    init_database(db_path)

    with get_connection(db_path) as connection:
        names = [
            row[0]
            for row in connection.execute(
                "SELECT keyword FROM keywords ORDER BY id"
            ).fetchall()
        ]
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }

    assert len(names) == len(BUILTIN_KEYWORDS) == 30
    assert len(names) == len(set(names))
    assert {"keywords", "crawled_items", "product_candidates"} <= tables


def test_keyword_can_be_disabled(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)
    with get_connection(db_path) as connection:
        keyword_id = connection.execute(
            "SELECT id FROM keywords WHERE keyword = ?", ("遮阳棚",)
        ).fetchone()[0]

    set_keyword_enabled(keyword_id, False, db_path)

    with get_connection(db_path) as connection:
        enabled = connection.execute(
            "SELECT enabled FROM keywords WHERE id = ?", (keyword_id,)
        ).fetchone()[0]
    assert enabled == 0


def test_same_link_is_updated_within_same_day(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)
    item = {
        "keyword": "遮阳棚",
        "title": "商用遮阳棚",
        "price": 300.0,
        "want_count": 10,
        "location": "杭州",
        "seller_type": "",
        "item_url": "https://www.goofish.com/item?id=1",
        "image_url": "",
        "raw_text": "商用遮阳棚 ¥300 10人想要",
        "crawl_date": date.today().isoformat(),
    }

    upsert_crawled_item(item, db_path)
    item["want_count"] = 21
    upsert_crawled_item(item, db_path)

    with get_connection(db_path) as connection:
        rows = connection.execute(
            "SELECT want_count FROM crawled_items"
        ).fetchall()
    assert [row[0] for row in rows] == [21]


def test_batch_saves_items_and_candidates(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)
    item = {
        "keyword": "烧烤炉",
        "title": "商用烧烤炉",
        "price": 500.0,
        "want_count": 25,
        "location": "",
        "seller_type": "",
        "item_url": "https://www.goofish.com/item?id=9",
        "image_url": "",
        "raw_text": "商用烧烤炉 25人想要",
        "crawl_date": "2026-06-30",
    }

    saved_items, saved_candidates = save_keyword_batch(
        "烧烤炉", [item], db_path
    )

    assert (saved_items, saved_candidates) == (1, 1)
    with get_connection(db_path) as connection:
        status = connection.execute(
            "SELECT recommendation_status FROM product_candidates"
        ).fetchone()[0]
    assert status == "可交付候选"


def test_saved_asset_record_is_upserted_and_listed(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)
    asset = {
        "item_url": "https://www.goofish.com/item?id=300",
        "title": "商用冷饮桶",
        "copy_text": "夏天摆摊冷饮桶，可发物流",
        "folder_path": "/tmp/商用冷饮桶",
        "image_count": 3,
        "source": "streamlit",
    }

    first_id = record_saved_asset(asset, db_path)
    second_id = record_saved_asset({**asset, "image_count": 4}, db_path)

    rows = list_saved_assets(db_path)
    assert first_id == second_id
    assert len(rows) == 1
    assert rows[0]["title"] == "商用冷饮桶"
    assert rows[0]["image_count"] == 4

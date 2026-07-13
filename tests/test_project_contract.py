from pathlib import Path

import crawler
from database import BUILTIN_KEYWORDS, get_connection, init_database
from rules import FILTER_TERMS, WEIGHT_TERMS


ROOT = Path(__file__).resolve().parents[1]

EXPECTED_KEYWORDS = [
    "遮阳棚", "雨棚", "伸缩遮阳棚", "烧烤炉", "烤串炉", "摆摊车", "小吃车",
    "冷饮桶", "果汁鼎", "制冰机", "儿童学习桌", "升降学习桌", "篮球架",
    "乒乓球桌", "空气循环扇", "工业风扇", "冷风机", "移动空调", "操作台",
    "发酵箱", "醒发箱", "猫别墅", "狗笼", "宠物烘干箱", "粉碎机", "铡草机",
    "脱粒机", "大棚膜", "不锈钢橱柜", "升降桌",
]
EXPECTED_FILTER_TERMS = {
    "服装", "女装", "鞋", "包", "化妆品", "口红", "护肤", "手机", "iphone",
    "平板", "耳机", "相机", "资料", "网课", "会员", "账号", "食品", "酒",
    "图书", "门票", "高仿", "莆田", "华强北",
}
EXPECTED_WEIGHT_TERMS = {
    "商用", "工业", "加厚", "工厂", "仓库", "设备", "机器", "摆摊", "餐饮",
    "农用", "养殖", "户外", "庭院", "阳台", "商铺", "遮阳", "制冷", "冷饮",
    "烧烤", "露营", "开学", "宠物", "大号", "发物流",
}


def test_required_delivery_files_exist():
    for name in ("requirements.txt", "README.md", "init_db.py", "crawler.py", "app.py"):
        assert (ROOT / name).is_file(), name


def test_builtin_keywords_and_rule_terms_match_request():
    assert [row[0] for row in BUILTIN_KEYWORDS] == EXPECTED_KEYWORDS
    assert set(FILTER_TERMS) == EXPECTED_FILTER_TERMS
    assert set(WEIGHT_TERMS) == EXPECTED_WEIGHT_TERMS


def test_database_tables_have_requested_columns(tmp_path):
    db_path = tmp_path / "contract.db"
    init_database(db_path)
    expected = {
        "keywords": [
            "id", "keyword", "category", "enabled", "priority", "note",
            "created_at", "updated_at",
        ],
        "crawled_items": [
            "id", "keyword", "title", "price", "want_count", "location",
            "seller_type", "item_url", "image_url", "raw_text", "crawl_date",
            "created_at",
        ],
        "product_candidates": [
            "id", "product_name", "keyword", "title", "price", "want_count",
            "item_url", "reason", "risk_level", "recommendation_status", "created_at",
        ],
    }
    with get_connection(db_path) as connection:
        for table, columns in expected.items():
            actual = [row[1] for row in connection.execute(f"PRAGMA table_info({table})")]
            assert actual == columns


def test_keyword_delay_is_fixed_to_safe_range():
    assert crawler.MIN_KEYWORD_DELAY_SECONDS == 10
    assert crawler.MAX_KEYWORD_DELAY_SECONDS == 30


def test_readme_contains_all_local_run_commands():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for command in (
        "pip install -r requirements.txt",
        "playwright install chromium",
        "python init_db.py",
        "python crawler.py",
        "streamlit run app.py",
    ):
        assert command in readme


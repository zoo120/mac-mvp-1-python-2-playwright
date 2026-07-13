# 闲鱼热卖品监测 MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建可在 Mac 本地运行的闲鱼关键词采集、SQLite 保存、规则筛选和 Streamlit 查看 MVP。

**Architecture:** 命令行采集器使用持久化的可见 Playwright Chromium，按关键词顺序抓取并节流；纯函数负责字段规范化和候选判断，数据库模块负责幂等写入。Streamlit 与采集器解耦，只通过 SQLite 管理关键词和展示结果。

**Tech Stack:** Python 3.10+、Playwright、SQLite、Streamlit、pandas、pytest

## Global Constraints

- 仅本地运行，不部署服务器，不实现登录与权限系统。
- 每个关键词最多抓取前 20 条；关键词之间必须随机等待 10–30 秒。
- 默认使用可见浏览器和持久化会话，登录或验证由用户手动处理。
- 单字段、单商品或单关键词失败不能中断整批采集，错误写入日志。
- 不实现自动私信、自动下单、自动评论、验证码绕过、代理池或并发采集。
- 三张业务表字段必须与设计规格一致。

---

## File Map

- `requirements.txt`：固定最低依赖版本。
- `.gitignore`：忽略数据库、浏览器会话、日志和 Python 缓存。
- `database.py`：表结构、关键词种子、连接、查询和幂等写入。
- `init_db.py`：数据库初始化入口。
- `rules.py`：候选品规则与可解释结果。
- `crawler.py`：纯解析函数、Playwright 提取、登录等待、节流和采集入口。
- `app.py`：Streamlit 四页面和筛选查询。
- `README.md`：Mac 本地安装和运行步骤。
- `tests/test_database.py`：初始化、种子、启停和快照幂等测试。
- `tests/test_rules.py`：候选判定优先级测试。
- `tests/test_crawler.py`：价格、想要数、URL 和卡片规范化测试。

### Task 1: 数据库结构与关键词种子

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `database.py`
- Create: `init_db.py`
- Create: `tests/test_database.py`

**Interfaces:**
- Produces: `init_database(db_path) -> None`
- Produces: `get_connection(db_path) -> sqlite3.Connection`
- Produces: `get_enabled_keywords(db_path) -> list[sqlite3.Row]`
- Produces: `set_keyword_enabled(keyword_id, enabled, db_path) -> None`
- Produces: `upsert_crawled_item(item, db_path, connection=None) -> int`
- Produces: `upsert_candidate(candidate, db_path, connection=None) -> int`

- [ ] **Step 1: 写数据库失败测试**

```python
from datetime import date

from database import (
    BUILTIN_KEYWORDS,
    get_connection,
    init_database,
    set_keyword_enabled,
    upsert_crawled_item,
)


def test_init_is_idempotent_and_seeds_all_keywords(tmp_path):
    db = tmp_path / "test.db"
    init_database(db)
    init_database(db)
    with get_connection(db) as conn:
        names = [row[0] for row in conn.execute("SELECT keyword FROM keywords")]
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
    assert len(names) == len(BUILTIN_KEYWORDS) == 30
    assert {"keywords", "crawled_items", "product_candidates"} <= tables


def test_keyword_can_be_disabled(tmp_path):
    db = tmp_path / "test.db"
    init_database(db)
    with get_connection(db) as conn:
        keyword_id = conn.execute(
            "SELECT id FROM keywords WHERE keyword = ?", ("遮阳棚",)
        ).fetchone()[0]
    set_keyword_enabled(keyword_id, False, db)
    with get_connection(db) as conn:
        enabled = conn.execute(
            "SELECT enabled FROM keywords WHERE id = ?", (keyword_id,)
        ).fetchone()[0]
    assert enabled == 0


def test_same_link_is_updated_within_same_day(tmp_path):
    db = tmp_path / "test.db"
    init_database(db)
    item = {
        "keyword": "遮阳棚", "title": "商用遮阳棚", "price": 300.0,
        "want_count": 10, "location": "杭州", "seller_type": "",
        "item_url": "https://www.goofish.com/item?id=1", "image_url": "",
        "raw_text": "商用遮阳棚 ¥300 10人想要", "crawl_date": date.today().isoformat(),
    }
    upsert_crawled_item(item, db)
    item["want_count"] = 21
    upsert_crawled_item(item, db)
    with get_connection(db) as conn:
        rows = conn.execute("SELECT want_count FROM crawled_items").fetchall()
    assert [row[0] for row in rows] == [21]
```

- [ ] **Step 2: 运行测试确认因模块不存在而失败**

Run: `python -m pytest tests/test_database.py -q`

Expected: FAIL，包含 `ModuleNotFoundError: No module named 'database'`。

- [ ] **Step 3: 实现数据库最小功能**

`database.py` 使用 `sqlite3.Row`、外部可传数据库路径、`CREATE TABLE IF NOT EXISTS`、部分唯一索引：

```python
conn.execute("""
CREATE UNIQUE INDEX IF NOT EXISTS uq_crawled_daily_link
ON crawled_items(keyword, item_url, crawl_date)
WHERE item_url IS NOT NULL AND item_url <> ''
""")
conn.execute("""
INSERT INTO crawled_items(
  keyword,title,price,want_count,location,seller_type,item_url,image_url,
  raw_text,crawl_date
) VALUES(:keyword,:title,:price,:want_count,:location,:seller_type,:item_url,
         :image_url,:raw_text,:crawl_date)
ON CONFLICT(keyword,item_url,crawl_date) WHERE item_url IS NOT NULL AND item_url <> ''
DO UPDATE SET title=excluded.title,price=excluded.price,
              want_count=excluded.want_count,location=excluded.location,
              seller_type=excluded.seller_type,image_url=excluded.image_url,
              raw_text=excluded.raw_text
""", item)
```

三张 `CREATE TABLE` 必须逐字段实现规格；关键词种子为 30 个 `(keyword, category, priority, note)` 元组，并以 `ON CONFLICT(keyword) DO NOTHING` 写入。`init_db.py` 只调用 `init_database()` 并打印数据库绝对路径。

- [ ] **Step 4: 运行数据库测试确认通过**

Run: `python -m pytest tests/test_database.py -q`

Expected: `3 passed`。

### Task 2: 候选品判定规则

**Files:**
- Create: `rules.py`
- Create: `tests/test_rules.py`

**Interfaces:**
- Produces: `CandidateDecision(product_name, reason, risk_level, recommendation_status)`
- Produces: `evaluate_item(item: Mapping[str, object]) -> CandidateDecision`

- [ ] **Step 1: 写规则失败测试**

```python
import pytest

from rules import evaluate_item


@pytest.mark.parametrize("title", ["iPhone 手机", "高仿莆田鞋", "摄影网课资料"])
def test_filter_terms_are_not_recommended(title):
    result = evaluate_item({"title": title, "price": 999, "want_count": 100})
    assert result.recommendation_status == "不建议"
    assert result.risk_level == "高"


def test_weighted_high_demand_is_delivery_candidate():
    result = evaluate_item({"title": "商用烧烤炉 发物流", "price": 500, "want_count": 20})
    assert result.recommendation_status == "可交付候选"
    assert "商用" in result.reason


def test_weighted_high_price_is_observable():
    result = evaluate_item({"title": "工业大号风扇", "price": 200, "want_count": 3})
    assert result.recommendation_status == "可观察"
    assert result.risk_level == "低"


def test_unweighted_cheap_item_is_not_recommended():
    result = evaluate_item({"title": "桌面小挂钩", "price": 9.9, "want_count": 50})
    assert result.recommendation_status == "不建议"
    assert "低价" in result.reason
```

- [ ] **Step 2: 运行规则测试确认因模块不存在而失败**

Run: `python -m pytest tests/test_rules.py -q`

Expected: FAIL，包含 `ModuleNotFoundError: No module named 'rules'`。

- [ ] **Step 3: 实现按优先级判定的纯函数**

```python
from dataclasses import dataclass

FILTER_TERMS = ("服装", "女装", "鞋", "包", "化妆品", "口红", "护肤", "手机",
                "iphone", "平板", "耳机", "相机", "资料", "网课", "会员", "账号",
                "食品", "酒", "图书", "门票", "高仿", "莆田", "华强北")
WEIGHT_TERMS = ("商用", "工业", "加厚", "工厂", "仓库", "设备", "机器", "摆摊",
                "餐饮", "农用", "养殖", "户外", "庭院", "阳台", "商铺", "遮阳",
                "制冷", "冷饮", "烧烤", "露营", "开学", "宠物", "大号", "发物流")
CHEAP_PRICE_MAX = 30.0
HIGH_PRICE_MIN = 200.0
HIGH_WANT_MIN = 20

@dataclass(frozen=True)
class CandidateDecision:
    product_name: str
    reason: str
    risk_level: str
    recommendation_status: str
```

`evaluate_item` 将标题转为小写，收集实际命中词；先判断过滤词，再判断低价无加权词，再判断加权且高想要数，再判断加权且高价格，最后返回普通“可观察”。空价格与空想要数不得按零值触发阈值。

- [ ] **Step 4: 运行规则测试确认通过**

Run: `python -m pytest tests/test_rules.py -q`

Expected: `6 passed`。

### Task 3: 页面字段规范化与搜索 URL

**Files:**
- Create: `crawler.py`
- Create: `tests/test_crawler.py`

**Interfaces:**
- Produces: `parse_price(text) -> float | None`
- Produces: `parse_want_count(text) -> int | None`
- Produces: `absolute_item_url(url) -> str`
- Produces: `normalize_card(raw, keyword, crawl_date) -> dict`
- Produces: `build_search_url(keyword) -> str`

- [ ] **Step 1: 写解析失败测试**

```python
from crawler import (
    absolute_item_url,
    build_search_url,
    normalize_card,
    parse_price,
    parse_want_count,
)


def test_price_supports_currency_and_decimals():
    assert parse_price("¥ 1,299.50") == 1299.5
    assert parse_price("价格面议") is None


def test_want_count_supports_plain_and_wan_units():
    assert parse_want_count("35人想要") == 35
    assert parse_want_count("1.2万想要") == 12000
    assert parse_want_count("暂无热度") is None


def test_relative_item_url_becomes_absolute():
    assert absolute_item_url("/item?id=1") == "https://www.goofish.com/item?id=1"


def test_card_uses_raw_text_as_fallback():
    result = normalize_card(
        {"title": "", "text": "商用烤串炉 ¥699 23人想要 杭州",
         "href": "/item?id=2", "image": "//img.example/a.jpg"},
        "烤串炉", "2026-06-30",
    )
    assert result["title"] == "商用烤串炉"
    assert result["price"] == 699.0
    assert result["want_count"] == 23
    assert result["item_url"].startswith("https://www.goofish.com/")


def test_search_url_is_encoded():
    assert "%E9%81%AE%E9%98%B3%E6%A3%9A" in build_search_url("遮阳棚")
```

- [ ] **Step 2: 运行解析测试确认因函数缺失而失败**

Run: `python -m pytest tests/test_crawler.py -q`

Expected: FAIL，包含无法从 `crawler` 导入目标函数。

- [ ] **Step 3: 实现纯解析函数**

```python
PRICE_RE = re.compile(r"(?:¥|￥|价格[:：]?\s*)\s*([0-9][0-9,]*(?:\.[0-9]+)?)")
WANT_RE = re.compile(r"([0-9]+(?:\.[0-9]+)?)\s*(万)?\s*(?:人)?想要")

def parse_want_count(text):
    match = WANT_RE.search(text or "")
    if not match:
        return None
    value = float(match.group(1)) * (10000 if match.group(2) else 1)
    return int(value)

def build_search_url(keyword):
    return "https://www.goofish.com/search?q=" + quote_plus(keyword)
```

`normalize_card` 清理空白，优先结构化标题和价格，缺失时从全文取第一段非价格文本及正则结果；协议相对图片补 `https:`，相对商品链接以 `https://www.goofish.com` 补全。地点和卖家类型无法可靠判断时保存空字符串。

- [ ] **Step 4: 运行解析测试确认通过**

Run: `python -m pytest tests/test_crawler.py -q`

Expected: `5 passed`。

### Task 4: Playwright 采集、事务写入和错误恢复

**Files:**
- Modify: `crawler.py`
- Modify: `database.py`
- Modify: `tests/test_database.py`

**Interfaces:**
- Consumes: `normalize_card`, `evaluate_item`, `upsert_crawled_item`, `upsert_candidate`
- Produces: `save_keyword_batch(keyword, items, db_path) -> tuple[int, int]`
- Produces: `async crawl_keyword(page, keyword, limit) -> list[dict]`
- Produces: `async run_crawler(keyword=None, limit=20, db_path=DEFAULT_DB_PATH) -> None`

- [ ] **Step 1: 写批量保存失败测试**

```python
from crawler import save_keyword_batch

def test_batch_saves_items_and_candidates(tmp_path):
    db = tmp_path / "test.db"
    init_database(db)
    item = {
        "keyword": "烧烤炉", "title": "商用烧烤炉", "price": 500.0,
        "want_count": 25, "location": "", "seller_type": "",
        "item_url": "https://www.goofish.com/item?id=9", "image_url": "",
        "raw_text": "商用烧烤炉 25人想要", "crawl_date": "2026-06-30",
    }
    saved_items, saved_candidates = save_keyword_batch("烧烤炉", [item], db)
    assert (saved_items, saved_candidates) == (1, 1)
    with get_connection(db) as conn:
        status = conn.execute(
            "SELECT recommendation_status FROM product_candidates"
        ).fetchone()[0]
    assert status == "可交付候选"
```

- [ ] **Step 2: 运行单测确认 `save_keyword_batch` 缺失**

Run: `python -m pytest tests/test_database.py::test_batch_saves_items_and_candidates -q`

Expected: FAIL，包含 `ImportError`。

- [ ] **Step 3: 实现事务保存和候选映射**

```python
def save_keyword_batch(keyword, items, db_path=DEFAULT_DB_PATH):
    with get_connection(db_path) as conn:
        for item in items:
            upsert_crawled_item(item, db_path, connection=conn)
            decision = evaluate_item(item)
            upsert_candidate({
                "product_name": decision.product_name,
                "keyword": keyword,
                "title": item["title"], "price": item["price"],
                "want_count": item["want_count"], "item_url": item["item_url"],
                "reason": decision.reason, "risk_level": decision.risk_level,
                "recommendation_status": decision.recommendation_status,
            }, db_path, connection=conn)
    return len(items), len(items)
```

- [ ] **Step 4: 实现浏览器主流程**

`crawl_keyword` 使用候选卡片选择器：`a[href*='/item']`、`a[href*='item?id=']`、`[data-testid*='item']`；在卡片上通过一次 `evaluate` 返回 `title/text/href/image/price/location`，逐条 `try/except` 后规范化。选择器均无结果时记录警告并返回空列表。

`run_crawler` 使用 `async_playwright().start()` 和 `chromium.launch_persistent_context(user_data_dir='.playwright-profile', headless=False)`；捕获每个关键词异常，记录后继续；两个关键词间调用 `asyncio.sleep(random.uniform(10, 30))`。页面正文含“登录”“验证码”“安全验证”时提示用户手动完成并通过 `input()` 继续。

命令行参数：`--keyword`、`--limit`、`--db`；`--limit` 通过 argparse 限制为 1–20。日志写 `logs/crawler.log` 和标准输出。

- [ ] **Step 5: 运行全部核心测试**

Run: `python -m pytest tests -q`

Expected: 所有测试通过，无网络访问。

### Task 5: Streamlit 四页面与使用文档

**Files:**
- Create: `app.py`
- Create: `README.md`

**Interfaces:**
- Consumes: SQLite 三张表和 `set_keyword_enabled`
- Produces: 四个侧边栏页面“今日概览、关键词管理、采集结果、候选品”

- [ ] **Step 1: 在 `app.py` 实现稳定查询辅助函数**

```python
def read_df(sql, params=()):
    with get_connection(DEFAULT_DB_PATH) as conn:
        return pd.read_sql_query(sql, conn, params=params)

def ensure_ready():
    init_database(DEFAULT_DB_PATH)
```

页面顶部设置 `st.set_page_config(page_title="闲鱼热卖品监测", layout="wide")`。侧边栏用 `st.radio` 选择四页面。

- [ ] **Step 2: 实现今日概览与关键词启停**

今日概览用三个 SQL 分别统计 `crawl_date = date('now','localtime')`、`enabled = 1`、候选 `date(created_at,'localtime') = date('now','localtime')`，用 `st.metric` 展示。

关键词管理使用 `st.data_editor`，只允许编辑 `enabled` 列；保存按钮比较原始与编辑数据，对变化行调用 `set_keyword_enabled`，随后 `st.rerun()`。

- [ ] **Step 3: 实现采集结果与候选品筛选**

采集结果页面提供关键词多选、价格滑块和最低想要数；仅在用户启用数值过滤时向 SQL 添加 `price IS NOT NULL` 或 `want_count IS NOT NULL`。候选品页面提供关键词、状态、风险多选。

候选表使用：

```python
st.dataframe(
    df,
    use_container_width=True,
    hide_index=True,
    column_config={"item_url": st.column_config.LinkColumn("商品链接")},
)
```

- [ ] **Step 4: 编写完整 README**

README 必须包括：创建虚拟环境、`pip install -r requirements.txt`、`playwright install chromium`、`python init_db.py`、单关键词验证、全量采集、手动登录说明、`streamlit run app.py`、数据库/日志/会话目录位置、平台结构变化排查方法和合规边界。

- [ ] **Step 5: 执行静态导入与帮助命令验证**

Run: `python -m compileall -q database.py init_db.py rules.py crawler.py app.py tests`

Expected: exit code 0。

Run: `python crawler.py --help`

Expected: exit code 0，显示 `--keyword`、`--limit`、`--db`。

### Task 6: 完整验证与交付检查

**Files:**
- Modify when required: files found failing verification

- [ ] **Step 1: 安装依赖并安装 Playwright Chromium**

Run: `python3 -m venv .venv`

Run: `.venv/bin/python -m pip install -r requirements.txt`

Run: `.venv/bin/playwright install chromium`

Expected: 三条命令均 exit code 0。

- [ ] **Step 2: 执行完整自动化测试**

Run: `.venv/bin/python -m pytest tests -q`

Expected: 所有测试通过，0 failed。

- [ ] **Step 3: 验证数据库可重复初始化**

Run: `.venv/bin/python init_db.py`

Run: `.venv/bin/python init_db.py`

Run: `.venv/bin/python -c "import sqlite3; c=sqlite3.connect('xianyu_monitor.db'); print(c.execute('select count(*) from keywords').fetchone()[0])"`

Expected: 输出 `30`。

- [ ] **Step 4: 启动 Streamlit 健康检查**

Run: `.venv/bin/streamlit run app.py --server.headless true --server.port 8501`

Expected: 日志显示本地地址且无 Python 异常；健康检查完成后停止进程。

- [ ] **Step 5: 对照规格逐项检查**

确认五个用户指定文件存在；三表字段完整；30 个关键词完整；过滤词和加权词完整；四页面存在；10–30 秒节流为强制值；README 四项运行步骤齐全；未出现自动私信、下单或评论能力。

## Plan Self-Review

- 规格覆盖：数据库、关键词、采集、容错、候选规则、四页面、文档和验证均有对应任务。
- 占位符扫描：计划不包含待实现占位项；所有阈值、接口和命令均已明确。
- 类型一致性：数据库路径接受 `str | Path`；采集记录和候选记录使用字典；规则输出统一为 `CandidateDecision`。
- 执行约束：实现阶段严格遵循每个任务的 RED → GREEN → REFACTOR 顺序。

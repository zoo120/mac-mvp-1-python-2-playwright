from datetime import date

from app import (
    PAGE_NAMES,
    build_lan_url,
    friendly_error_message,
    get_dashboard_summary,
    is_student_result_for_keyword,
    open_folder_for_streamlit,
    parse_saved_folder_from_message,
    query_student_results,
    run_student_keyword_search_for_streamlit,
    save_product_assets_for_streamlit,
    query_material_candidates,
    query_candidates,
    query_crawled_items,
)
from database import init_database, upsert_candidate, upsert_crawled_item


class CompletedProcessStub:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_app_exposes_required_pages():
    assert PAGE_NAMES == (
        "学员选品助手",
        "云端登录",
        "今日概览",
        "关键词管理",
        "采集结果",
        "候选品",
        "素材保存",
    )


def test_lan_url_is_built_from_ip_and_port():
    assert build_lan_url("192.168.1.8") == "http://192.168.1.8:8501"
    assert build_lan_url("192.168.1.8", 8600) == "http://192.168.1.8:8600"
    assert build_lan_url("") == "http://127.0.0.1:8501"


def test_empty_database_summary_counts_enabled_keywords(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    summary = get_dashboard_summary(db_path)

    assert summary == {
        "today_items": 0,
        "enabled_keywords": 30,
        "today_candidates": 0,
    }


def test_result_queries_apply_numeric_and_keyword_filters(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)
    today = date.today().isoformat()
    base = {
        "title": "商用遮阳棚",
        "price": 300.0,
        "want_count": 21,
        "location": "杭州",
        "seller_type": "商家",
        "item_url": "https://www.goofish.com/item?id=100",
        "image_url": "",
        "raw_text": "商用遮阳棚 ¥300 21人想要",
        "crawl_date": today,
    }
    upsert_crawled_item({"keyword": "遮阳棚", **base}, db_path)
    upsert_crawled_item(
        {
            "keyword": "雨棚",
            **base,
            "title": "小雨棚",
            "price": 20.0,
            "item_url": "https://www.goofish.com/item?id=101",
        },
        db_path,
    )

    rows = query_crawled_items(
        db_path,
        keywords=["遮阳棚"],
        min_price=100,
        max_price=400,
        min_want_count=20,
    )

    assert [row["title"] for row in rows] == ["商用遮阳棚"]


def test_candidate_query_filters_status_and_risk(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)
    upsert_candidate(
        {
            "product_name": "商用烧烤炉",
            "keyword": "烧烤炉",
            "title": "商用烧烤炉",
            "price": 500,
            "want_count": 30,
            "item_url": "https://www.goofish.com/item?id=200",
            "reason": "命中加权词",
            "risk_level": "低",
            "recommendation_status": "可交付候选",
        },
        db_path,
    )

    rows = query_candidates(
        db_path,
        keywords=["烧烤炉"],
        statuses=["可交付候选"],
        risk_levels=["低"],
    )

    assert len(rows) == 1
    assert rows[0]["title"] == "商用烧烤炉"


def test_material_candidate_choices_only_include_items_with_links(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)
    upsert_candidate(
        {
            "product_name": "商用制冰机",
            "keyword": "制冰机",
            "title": "商用制冰机可发物流",
            "price": 1200,
            "want_count": 56,
            "item_url": "https://www.goofish.com/item?id=500",
            "reason": "命中加权词",
            "risk_level": "低",
            "recommendation_status": "可交付候选",
        },
        db_path,
    )
    upsert_candidate(
        {
            "product_name": "无链接商品",
            "keyword": "测试",
            "title": "无链接商品",
            "price": 100,
            "want_count": 1,
            "item_url": "",
            "reason": "",
            "risk_level": "中",
            "recommendation_status": "可观察",
        },
        db_path,
    )

    rows = query_material_candidates(db_path)

    assert len(rows) == 1
    assert rows[0]["title"] == "商用制冰机可发物流"
    assert rows[0]["item_url"] == "https://www.goofish.com/item?id=500"


def test_student_results_are_sorted_by_want_count_then_price(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)
    today = date.today().isoformat()
    base = {
        "keyword": "床垫",
        "location": "",
        "seller_type": "",
        "image_url": "",
        "raw_text": "",
        "crawl_date": today,
    }
    upsert_crawled_item(
        {
            **base,
            "title": "普通床垫",
            "price": 300,
            "want_count": 10,
            "item_url": "https://www.goofish.com/item?id=601",
        },
        db_path,
    )
    upsert_crawled_item(
        {
            **base,
            "title": "热度高床垫",
            "price": 100,
            "want_count": 66,
            "item_url": "https://www.goofish.com/item?id=602",
        },
        db_path,
    )
    upsert_crawled_item(
        {
            **base,
            "title": "高价床垫",
            "price": 900,
            "want_count": 66,
            "item_url": "https://www.goofish.com/item?id=603",
        },
        db_path,
    )

    rows = query_student_results("床垫", db_path)

    assert [row["title"] for row in rows] == ["高价床垫", "热度高床垫", "普通床垫"]


def test_student_result_keyword_guard_prevents_wrong_product_save():
    assert is_student_result_for_keyword({"keyword": "床垫"}, "床垫")
    assert not is_student_result_for_keyword({"keyword": "狗笼"}, "床垫")


def test_student_search_uses_child_process_not_inline_event_loop(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)
    calls = []

    def fake_runner(command, **kwargs):
        calls.append((command, kwargs))
        return CompletedProcessStub(stdout="ok")

    result = run_student_keyword_search_for_streamlit(
        "床垫",
        20,
        db_path,
        runner=fake_runner,
    )

    command = calls[0][0]
    assert "crawler.py" in command[1]
    assert "--student-keyword" in command
    assert "床垫" in command
    assert result == (0, 0)


def test_student_search_child_process_failure_is_reported(tmp_path):
    db_path = tmp_path / "test.db"
    init_database(db_path)

    def fake_runner(command, **kwargs):
        return CompletedProcessStub(returncode=1, stderr="需要登录")

    try:
        run_student_keyword_search_for_streamlit("床垫", 20, db_path, runner=fake_runner)
    except RuntimeError as exc:
        assert "闲鱼要求登录或安全验证" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")


def test_tunnel_connection_error_is_translated_for_learners():
    message = friendly_error_message(
        "Page.goto: net::ERR_TUNNEL_CONNECTION_FAILED at https://www.goofish.com/search"
    )

    assert "网络代理/VPN连接失败" in message
    assert "ERR_TUNNEL" not in message


def test_asset_save_uses_child_process_not_inline_event_loop(tmp_path):
    calls = []

    def fake_runner(command, **kwargs):
        calls.append((command, kwargs))
        return CompletedProcessStub(stdout="已保存到：/tmp/demo，图片 1 张。")

    message = save_product_assets_for_streamlit(
        "https://www.goofish.com/item?id=1",
        "床垫",
        tmp_path / "test.db",
        runner=fake_runner,
    )

    command = calls[0][0]
    assert "asset_saver.py" in command[1]
    assert "--item-url" in command
    assert "https://www.goofish.com/item?id=1" in command
    assert message == "已保存到：/tmp/demo，图片 1 张。"


def test_saved_folder_path_can_be_parsed_from_success_message():
    assert (
        parse_saved_folder_from_message("已保存到：/tmp/demo folder，图片 5 张。")
        == "/tmp/demo folder"
    )
    assert parse_saved_folder_from_message("保存失败") == ""


def test_open_folder_uses_finder_command(tmp_path):
    calls = []

    def fake_runner(command, **kwargs):
        calls.append((command, kwargs))

    open_folder_for_streamlit(tmp_path, runner=fake_runner)

    assert calls == [(["open", str(tmp_path)], {"check": True})]

import asyncio

from crawler import (
    absolute_image_url,
    absolute_item_url,
    build_search_url,
    crawl_keyword_sequence,
    crawl_student_keyword_once,
    normalize_card,
    needs_manual_intervention,
    parse_location,
    parse_price,
    parse_limit,
    parse_want_count,
    should_wait_for_manual_intervention,
)
import argparse
import pytest


def test_price_supports_currency_and_decimals():
    assert parse_price("¥ 1,299.50") == 1299.5
    assert parse_price("价格：899元") == 899.0
    assert parse_price("价格面议") is None


def test_want_count_supports_plain_and_wan_units():
    assert parse_want_count("35人想要") == 35
    assert parse_want_count("1.2万想要") == 12000
    assert parse_want_count("暂无热度") is None


def test_relative_urls_become_absolute():
    assert (
        absolute_item_url("/item?id=1")
        == "https://www.goofish.com/item?id=1"
    )
    assert absolute_image_url("//img.example/a.jpg") == "https://img.example/a.jpg"


def test_card_uses_raw_text_as_fallback():
    result = normalize_card(
        {
            "title": "",
            "text": "商用烤串炉 ¥699 23人想要",
            "href": "/item?id=2",
            "image": "//img.example/a.jpg",
            "location": "杭州",
            "seller_type": "商家",
        },
        "烤串炉",
        "2026-06-30",
    )

    assert result["title"] == "商用烤串炉"
    assert result["price"] == 699.0
    assert result["want_count"] == 23
    assert result["location"] == "杭州"
    assert result["seller_type"] == "商家"
    assert result["item_url"].startswith("https://www.goofish.com/")


def test_structured_values_take_priority_over_raw_text():
    result = normalize_card(
        {
            "title": "工业风扇",
            "text": "其他标题 ¥99 2人想要",
            "price": "399",
            "want_count": "31",
            "href": "https://www.goofish.com/item?id=3",
            "image": "",
        },
        "工业风扇",
        "2026-06-30",
    )

    assert result["title"] == "工业风扇"
    assert result["price"] == 399.0
    assert result["want_count"] == 31


def test_search_url_is_encoded():
    assert "%E9%81%AE%E9%98%B3%E6%A3%9A" in build_search_url("遮阳棚")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("商品标题 ¥ 27 296人想要 山东", "山东"),
        ("商品标题 ¥ 33 累计降价2.00元 广东 回复超快", "广东"),
        ("商品标题 ¥ 45 22人想要 湖北 回复超快", "湖北"),
        ("商品标题 ¥ 45 22人想要", ""),
    ],
)
def test_location_falls_back_to_province_near_card_end(text, expected):
    assert parse_location(text) == expected


def test_structured_location_takes_priority_over_raw_fallback():
    result = normalize_card(
        {"text": "商品 ¥99 山东", "location": "杭州"},
        "测试",
        "2026-07-01",
    )
    assert result["location"] == "杭州"


def test_limit_is_restricted_to_one_through_twenty():
    assert parse_limit("1") == 1
    assert parse_limit("20") == 20
    with pytest.raises(argparse.ArgumentTypeError):
        parse_limit("0")
    with pytest.raises(argparse.ArgumentTypeError):
        parse_limit("21")


@pytest.mark.parametrize(
    "text",
    [
        "请登录后继续",
        "请完成安全验证",
        "输入验证码",
        "登录后可以更懂你，推荐你喜欢的商品！",
        "立即登录",
    ],
)
def test_manual_intervention_phrases_are_detected(text):
    assert needs_manual_intervention(text)


def test_normal_results_do_not_request_manual_intervention():
    assert not needs_manual_intervention("为你找到以下闲置好物")


def test_login_recommendation_does_not_pause_when_results_are_loaded():
    assert not should_wait_for_manual_intervention("立即登录", card_count=20)


def test_login_recommendation_pauses_when_results_are_absent():
    assert should_wait_for_manual_intervention("立即登录", card_count=0)


def test_keyword_failure_does_not_stop_following_keywords(tmp_path):
    calls = []
    sleeps = []

    async def fake_crawl(page, keyword, limit):
        calls.append(keyword)
        if keyword == "失败词":
            raise RuntimeError("页面结构变化")
        return []

    def fake_save(keyword, items, db_path):
        return (len(items), len(items))

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    asyncio.run(
        crawl_keyword_sequence(
            page=object(),
            keyword_rows=[{"keyword": "失败词"}, {"keyword": "正常词"}],
            limit=3,
            db_path=tmp_path / "test.db",
            crawl_func=fake_crawl,
            save_func=fake_save,
            sleep_func=fake_sleep,
            delay_func=lambda minimum, maximum: 10.0,
        )
    )

    assert calls == ["失败词", "正常词"]
    assert sleeps == [10.0]


def test_student_keyword_crawl_accepts_arbitrary_keyword(tmp_path):
    calls = []
    saved = []

    async def fake_crawl(page, keyword, limit, **kwargs):
        calls.append((keyword, limit, kwargs))
        return []

    def fake_save(keyword, items, db_path):
        saved.append((keyword, items, db_path))
        return (0, 0)

    asyncio.run(
        crawl_student_keyword_once(
            page=object(),
            keyword="床垫",
            limit=20,
            db_path=tmp_path / "test.db",
            crawl_func=fake_crawl,
            save_func=fake_save,
        )
    )

    assert calls == [("床垫", 20, {"manual_intervention_mode": "poll"})]
    assert saved[0][0] == "床垫"

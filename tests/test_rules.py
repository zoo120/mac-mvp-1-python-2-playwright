import pytest

from rules import evaluate_item


@pytest.mark.parametrize("title", ["iPhone 手机", "高仿莆田鞋", "摄影网课资料"])
def test_filter_terms_are_not_recommended(title):
    result = evaluate_item({"title": title, "price": 999, "want_count": 100})

    assert result.recommendation_status == "不建议"
    assert result.risk_level == "高"


def test_weighted_high_demand_is_delivery_candidate():
    result = evaluate_item(
        {"title": "商用烧烤炉 发物流", "price": 500, "want_count": 20}
    )

    assert result.recommendation_status == "可交付候选"
    assert result.risk_level == "低"
    assert "商用" in result.reason
    assert "20" in result.reason


def test_weighted_high_price_is_observable():
    result = evaluate_item({"title": "工业大号风扇", "price": 200, "want_count": 3})

    assert result.recommendation_status == "可观察"
    assert result.risk_level == "低"
    assert "200" in result.reason


def test_unweighted_cheap_item_is_not_recommended():
    result = evaluate_item({"title": "桌面小挂钩", "price": 9.9, "want_count": 50})

    assert result.recommendation_status == "不建议"
    assert result.risk_level == "中"
    assert "低价" in result.reason


def test_missing_price_does_not_count_as_cheap():
    result = evaluate_item({"title": "普通置物架", "price": None, "want_count": None})

    assert result.recommendation_status == "可观察"
    assert result.risk_level == "中"


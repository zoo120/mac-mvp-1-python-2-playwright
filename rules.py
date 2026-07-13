"""Transparent candidate scoring rules for the MVP."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


FILTER_TERMS = (
    "服装",
    "女装",
    "鞋",
    "包",
    "化妆品",
    "口红",
    "护肤",
    "手机",
    "iphone",
    "平板",
    "耳机",
    "相机",
    "资料",
    "网课",
    "会员",
    "账号",
    "食品",
    "酒",
    "图书",
    "门票",
    "高仿",
    "莆田",
    "华强北",
)

WEIGHT_TERMS = (
    "商用",
    "工业",
    "加厚",
    "工厂",
    "仓库",
    "设备",
    "机器",
    "摆摊",
    "餐饮",
    "农用",
    "养殖",
    "户外",
    "庭院",
    "阳台",
    "商铺",
    "遮阳",
    "制冷",
    "冷饮",
    "烧烤",
    "露营",
    "开学",
    "宠物",
    "大号",
    "发物流",
)

CHEAP_PRICE_MAX = 30.0
HIGH_PRICE_MIN = 200.0
HIGH_WANT_MIN = 20


@dataclass(frozen=True)
class CandidateDecision:
    product_name: str
    reason: str
    risk_level: str
    recommendation_status: str


def _clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def evaluate_item(item: Mapping[str, Any]) -> CandidateDecision:
    """Evaluate one item using ordered, human-readable MVP rules."""
    title = _clean_text(item.get("title"))
    product_name = title or _clean_text(item.get("keyword")) or "未命名商品"
    normalized_title = title.casefold()
    price = _number(item.get("price"))
    want_count = _number(item.get("want_count"))

    filter_hits = [term for term in FILTER_TERMS if term.casefold() in normalized_title]
    weight_hits = [term for term in WEIGHT_TERMS if term.casefold() in normalized_title]

    if filter_hits:
        return CandidateDecision(
            product_name=product_name,
            reason=f"命中过滤词：{'、'.join(filter_hits)}",
            risk_level="高",
            recommendation_status="不建议",
        )

    if price is not None and price <= CHEAP_PRICE_MAX and not weight_hits:
        return CandidateDecision(
            product_name=product_name,
            reason=f"价格 {price:g} 元，属于低价小百货区间，且未命中加权词",
            risk_level="中",
            recommendation_status="不建议",
        )

    if weight_hits and want_count is not None and want_count >= HIGH_WANT_MIN:
        return CandidateDecision(
            product_name=product_name,
            reason=(
                f"命中加权词：{'、'.join(weight_hits)}；"
                f"想要数 {int(want_count)}，达到候选阈值 {HIGH_WANT_MIN}"
            ),
            risk_level="低",
            recommendation_status="可交付候选",
        )

    if weight_hits and price is not None and price >= HIGH_PRICE_MIN:
        return CandidateDecision(
            product_name=product_name,
            reason=(
                f"命中加权词：{'、'.join(weight_hits)}；"
                f"价格 {price:g} 元，达到观察阈值 {HIGH_PRICE_MIN:g}"
            ),
            risk_level="低",
            recommendation_status="可观察",
        )

    details = []
    if weight_hits:
        details.append(f"命中加权词：{'、'.join(weight_hits)}，但热度或价格未达高阈值")
    else:
        details.append("未命中过滤词，暂未命中明确加权条件")
    if price is None:
        details.append("价格缺失")
    if want_count is None:
        details.append("想要数缺失")
    return CandidateDecision(
        product_name=product_name,
        reason="；".join(details),
        risk_level="中",
        recommendation_status="可观察",
    )


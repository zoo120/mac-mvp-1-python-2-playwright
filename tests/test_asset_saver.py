import json

import pytest

from asset_saver import (
    extract_detail_copy,
    filter_image_urls,
    normalize_detail_payload,
    safe_folder_name,
    save_material_files,
    validate_item_url,
)


def test_safe_folder_name_removes_mac_unsafe_characters():
    assert safe_folder_name("商用/烧烤炉: 90cm?*") == "商用_烧烤炉_90cm"
    assert safe_folder_name("") == "商品素材"


def test_normalize_detail_payload_prefers_page_title_and_falls_back_to_hint():
    payload = normalize_detail_payload(
        {
            "title": "  商用制冰机  ",
            "description": "九成新，可发物流",
            "images": ["//img.example/a.jpg", "https://img.example/a.jpg"],
            "raw_text": "页面正文",
        },
        "https://www.goofish.com/item?id=123",
        title_hint="列表标题",
    )

    assert payload["title"] == "商用制冰机"
    assert payload["description"] == "九成新，可发物流"
    assert payload["item_url"] == "https://www.goofish.com/item?id=123"
    assert payload["images"] == ["https://img.example/a.jpg"]


def test_normalize_detail_payload_uses_title_hint_when_page_title_missing():
    payload = normalize_detail_payload(
        {"title": "", "description": "", "images": [], "raw_text": "正文"},
        "https://www.goofish.com/item?id=124",
        title_hint="候选标题",
    )

    assert payload["title"] == "候选标题"
    assert payload["description"] == "正文"


def test_save_material_files_writes_copy_json_and_images(tmp_path):
    payload = {
        "title": "商用烧烤炉",
        "description": "适合摆摊，可发物流",
        "item_url": "https://www.goofish.com/item?id=200",
        "images": ["https://img.example/a.jpg"],
        "raw_text": "商用烧烤炉 适合摆摊",
    }

    result = save_material_files(
        payload,
        [("https://img.example/a.jpg", b"fake-image-bytes", "jpg")],
        tmp_path,
    )

    folder = result["folder_path"]
    assert folder.name.startswith("商用烧烤炉")
    assert (folder / "文案.txt").read_text(encoding="utf-8") == "适合摆摊，可发物流\n"
    saved_json = json.loads((folder / "商品信息.json").read_text(encoding="utf-8"))
    assert saved_json["item_url"] == "https://www.goofish.com/item?id=200"
    assert (folder / "images" / "图片1.jpg").read_bytes() == b"fake-image-bytes"
    assert result["image_count"] == 1


@pytest.mark.parametrize(
    "url",
    [
        "https://www.goofish.com/item?id=1",
        "https://h5.m.goofish.com/item?id=1",
        "https://market.m.taobao.com/app/idleFish-F2e/widle-taobao-rax/page-detail?id=1",
    ],
)
def test_validate_item_url_accepts_xianyu_domains(url):
    assert validate_item_url(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "",
        "not-a-url",
        "https://example.com/item?id=1",
    ],
)
def test_validate_item_url_rejects_unsafe_urls(url):
    with pytest.raises(ValueError):
        validate_item_url(url)


def test_filter_image_urls_keeps_real_product_images_once():
    urls = filter_image_urls(
        [
            "",
            "data:image/png;base64,aaa",
            "//img.alicdn.com/a.jpg",
            "https://img.alicdn.com/a.jpg",
            "https://example.com/icon.svg",
        ]
    )

    assert urls == ["https://img.alicdn.com/a.jpg"]


def test_extract_detail_copy_removes_page_chrome_and_recommendations():
    raw_text = (
        "搜索 网页版发闲置功能又升级啦！ 甜宠宝藏 石家庄 32分钟前来过 "
        "¥ 18.5 - 199.98 包邮 9440人想要 9万浏览 "
        "描述不符包邮退 满足条件时，买家可退货且运费由卖家承担 "
        "批发狗狗笼子狗围栏 家用室内中大型犬宠物围栏栅栏 自由组合带隔离门 "
        "拍下即发超大空间加粗狗围栏 一个仅需18.5元 全新未拆封 "
        "买前须知: 1.由于笼具是大件商品，退货需承担运费。"
        "展开 聊一聊 立即购买 收藏 为你推荐 清仓价！六层猫爬架 ¥ 20"
    )

    copy = extract_detail_copy(raw_text)

    assert copy.startswith("批发狗狗笼子狗围栏")
    assert "买前须知" in copy
    assert "搜索" not in copy
    assert "聊一聊" not in copy
    assert "为你推荐" not in copy


def test_normalize_detail_payload_uses_cleaned_detail_copy_from_raw_page_text():
    payload = normalize_detail_payload(
        {
            "title": "为你推荐",
            "description": "",
            "images": [],
            "raw_text": (
                "搜索 卖家信息 ¥ 160.00 658人想要 2万浏览 "
                "着急卖！网易严选同款升降床边桌！多功能气杆升降 可移动办公电脑桌/书桌，宜家同款风格！ "
                "办公学习小能手，一桌多用！桌面简约实用，承重稳 "
                "展开 聊一聊 立即购买 收藏 为你推荐 其他商品 ¥ 20"
            ),
        },
        "https://www.goofish.com/item?id=125",
        title_hint="网易严选同款升降床边桌",
    )

    assert payload["title"] == "网易严选同款升降床边桌"
    assert payload["description"].startswith("着急卖！网易严选同款升降床边桌")
    assert "为你推荐" not in payload["description"]


def test_normalize_detail_payload_ignores_short_guarantee_description():
    payload = normalize_detail_payload(
        {
            "title": "为你推荐",
            "description": "描述不符包邮退 满足条件时，买家可退货且运费由卖家承担",
            "images": [],
            "raw_text": (
                "搜索 卖家信息 ¥ 18.5 - 199.98 包邮 9440人想要 9万浏览 "
                "描述不符包邮退 满足条件时，买家可退货且运费由卖家承担 "
                "批发狗狗笼子狗围栏 家用室内中大型犬宠物围栏栅栏 自由组合带隔离门 "
                "拍下即发超大空间加粗狗围栏 一个仅需18.5元 全新未拆封 "
                "展开 聊一聊 立即购买 收藏 为你推荐 其他商品 ¥ 20"
            ),
        },
        "https://www.goofish.com/item?id=126",
        title_hint="狗狗围栏",
    )

    assert payload["description"].startswith("批发狗狗笼子狗围栏")
    assert "买家可退货且运费由卖家承担" not in payload["description"]

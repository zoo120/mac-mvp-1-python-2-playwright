"""Streamlit dashboard for the local Xianyu monitoring MVP."""

from __future__ import annotations

import os
import socket
import sqlite3
import subprocess
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from database import (
    DEFAULT_DB_PATH,
    get_connection,
    init_database,
    list_saved_assets,
    set_keyword_enabled,
)


PAGE_NAMES = (
    "学员选品助手",
    "云端登录",
    "今日概览",
    "关键词管理",
    "采集结果",
    "候选品",
    "素材保存",
)
PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_STUDENT_LIMIT = 10
DEFAULT_PORT = 8501
DEFAULT_CLOUD_LOGIN_SECONDS = 180


def _subprocess_error(completed: Any) -> str:
    message = str(getattr(completed, "stderr", "") or getattr(completed, "stdout", "") or "")
    return friendly_error_message(
        message.strip() or f"子进程退出码：{getattr(completed, 'returncode', '未知')}"
    )


def get_local_lan_ip() -> str:
    """Best-effort local LAN IP for same-Wi-Fi sharing."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return str(sock.getsockname()[0])
    except OSError:
        return "127.0.0.1"


def build_lan_url(ip_address: str, port: int = DEFAULT_PORT) -> str:
    value = str(ip_address or "").strip() or "127.0.0.1"
    return f"http://{value}:{int(port)}"


def is_online_deployment() -> bool:
    """Whether the app is running on the public server deployment."""
    return any(
        os.getenv(name)
        for name in (
            "XIANYU_DB_PATH",
            "XIANYU_SAVED_PRODUCTS_DIR",
            "XIANYU_PROFILE_DIR",
            "XIANYU_LOG_DIR",
            "XIANYU_HEADLESS",
        )
    )


def cloud_login_screenshot_path() -> Path:
    """Screenshot path used by the server-side Xianyu login helper."""
    explicit = os.getenv("XIANYU_LOGIN_SCREENSHOT")
    if explicit:
        return Path(explicit).expanduser()
    base = Path(os.getenv("XIANYU_LOG_DIR") or (PROJECT_DIR / "logs")).expanduser()
    return base / "xianyu_login.png"


def cloud_login_pid_path() -> Path:
    return cloud_login_screenshot_path().with_suffix(".pid")


def is_pid_running(pid: int) -> bool:
    """Best-effort process check that works on Linux/macOS."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def cloud_login_process_status() -> str:
    pid_file = cloud_login_pid_path()
    if not pid_file.exists():
        return "未启动"
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return "状态未知"
    return f"运行中（PID {pid}）" if is_pid_running(pid) else "已结束，可重新启动"


def start_cloud_login_session(
    *,
    wait_seconds: int = DEFAULT_CLOUD_LOGIN_SECONDS,
    keyword: str = "床垫",
) -> int:
    """Start a background server browser session for Xianyu login/verification."""
    screenshot_path = cloud_login_screenshot_path()
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path = cloud_login_pid_path()

    process = subprocess.Popen(
        [
            sys.executable,
            str(PROJECT_DIR / "cloud_login.py"),
            "--screenshot",
            str(screenshot_path),
            "--wait",
            str(max(30, int(wait_seconds))),
            "--keyword",
            str(keyword or "床垫"),
        ],
        cwd=str(PROJECT_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    pid_path.write_text(str(process.pid), encoding="utf-8")
    return int(process.pid)


def render_student_usage_help(st: Any) -> None:
    if is_online_deployment():
        st.write("这是线上版。把浏览器地址栏里的公网网址发给学员即可。")
        st.info(
            "给学员发的地址应该类似：http://你的公网IP。"
            "不要发 localhost，也不要发 172. 开头的内网地址。"
        )
        return

    lan_url = build_lan_url(get_local_lan_ip())
    st.write("这是本地版，只适合你自己电脑测试。")
    st.write("你自己打开：")
    st.code(build_lan_url("localhost"))
    st.write("如果学员和你在同一个 Wi‑Fi，临时测试可以打开：")
    st.code(lan_url)
    st.warning("全国学员使用必须部署到云服务器，然后发公网地址。")


def parse_saved_folder_from_message(message: str) -> str:
    """Extract the local saved folder path from asset_saver's success message."""
    text = str(message or "").strip()
    prefix = "已保存到："
    if prefix not in text:
        return ""
    after_prefix = text.split(prefix, 1)[1]
    return after_prefix.split("，图片", 1)[0].strip()


def open_folder_for_streamlit(
    folder_path: str,
    *,
    runner: Any = subprocess.run,
) -> None:
    """Open a saved folder in Finder on the local Mac."""
    path = Path(str(folder_path or "")).expanduser()
    if not path.exists() or not path.is_dir():
        raise ValueError("素材文件夹不存在，请先重新保存一次。")
    runner(["open", str(path)], check=True)


def friendly_error_message(message: str) -> str:
    """Convert common technical failures into learner-readable Chinese hints."""
    text = str(message or "").strip()
    if "ERR_TUNNEL_CONNECTION_FAILED" in text:
        return (
            "网络代理/VPN连接失败，程序打不开闲鱼。请先关闭 VPN/代理，"
            "或者在系统设置里关闭代理后，再点一次搜索。"
        )
    if "ERR_PROXY_CONNECTION_FAILED" in text:
        return "代理连接失败。请关闭代理/VPN 后，再点一次搜索。"
    if "ERR_NAME_NOT_RESOLVED" in text or "ERR_INTERNET_DISCONNECTED" in text:
        return "网络连接失败。请先确认 Mac 能正常打开网页，再点一次搜索。"
    if "闲鱼要求登录或安全验证" in text or "需要登录" in text or "安全验证" in text:
        if is_online_deployment():
            return "闲鱼要求登录或安全验证。管理员请打开左侧“云端登录”，先扫码/验证一次。"
        return "闲鱼要求登录或安全验证。请在弹出的浏览器里完成登录/验证后，再点一次搜索。"
    first_line = text.splitlines()[0] if text else "未知错误"
    return first_line[:240]


def run_student_keyword_search_for_streamlit(
    keyword: str,
    limit: int,
    db_path: str | Path = DEFAULT_DB_PATH,
    *,
    runner: Any = subprocess.run,
) -> tuple[int, int]:
    """Run learner keyword crawl in a child process to avoid Streamlit event-loop conflicts."""
    completed = runner(
        [
            sys.executable,
            str(PROJECT_DIR / "crawler.py"),
            "--student-keyword",
            str(keyword),
            "--limit",
            str(limit),
            "--db",
            str(db_path),
        ],
        cwd=str(PROJECT_DIR),
        capture_output=True,
        text=True,
        timeout=300,
    )
    if completed.returncode != 0:
        raise RuntimeError(_subprocess_error(completed))
    current_rows = query_student_results(keyword, db_path)
    return len(current_rows), len(current_rows)


def save_product_assets_for_streamlit(
    item_url: str,
    title_hint: str,
    db_path: str | Path = DEFAULT_DB_PATH,
    *,
    runner: Any = subprocess.run,
) -> str:
    """Save product assets in a child process to avoid Streamlit event-loop conflicts."""
    completed = runner(
        [
            sys.executable,
            str(PROJECT_DIR / "asset_saver.py"),
            "--item-url",
            str(item_url),
            "--title-hint",
            str(title_hint),
            "--db",
            str(db_path),
        ],
        cwd=str(PROJECT_DIR),
        capture_output=True,
        text=True,
        timeout=300,
    )
    if completed.returncode != 0:
        raise RuntimeError(_subprocess_error(completed))
    return str(completed.stdout or "").strip()


def _placeholders(values: Sequence[Any]) -> str:
    return ",".join("?" for _ in values)


def get_dashboard_summary(
    db_path: str | Path = DEFAULT_DB_PATH,
) -> dict[str, int]:
    with get_connection(db_path) as connection:
        today_items = connection.execute(
            "SELECT COUNT(*) FROM crawled_items WHERE crawl_date = date('now', 'localtime')"
        ).fetchone()[0]
        enabled_keywords = connection.execute(
            "SELECT COUNT(*) FROM keywords WHERE enabled = 1"
        ).fetchone()[0]
        today_candidates = connection.execute(
            """
            SELECT COUNT(*) FROM product_candidates
            WHERE date(created_at, 'localtime') = date('now', 'localtime')
            """
        ).fetchone()[0]
    return {
        "today_items": int(today_items),
        "enabled_keywords": int(enabled_keywords),
        "today_candidates": int(today_candidates),
    }


def query_crawled_items(
    db_path: str | Path = DEFAULT_DB_PATH,
    *,
    keywords: Sequence[str] | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    min_want_count: int | None = None,
    limit: int = 1_000,
) -> list[sqlite3.Row]:
    conditions: list[str] = []
    params: list[Any] = []
    if keywords:
        conditions.append(f"keyword IN ({_placeholders(keywords)})")
        params.extend(keywords)
    if min_price is not None:
        conditions.append("price IS NOT NULL AND price >= ?")
        params.append(min_price)
    if max_price is not None:
        conditions.append("price IS NOT NULL AND price <= ?")
        params.append(max_price)
    if min_want_count is not None:
        conditions.append("want_count IS NOT NULL AND want_count >= ?")
        params.append(min_want_count)

    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(max(1, int(limit)))
    with get_connection(db_path) as connection:
        return connection.execute(
            f"""
            SELECT id, keyword, title, price, want_count, location, seller_type,
                   item_url, image_url, crawl_date, created_at
            FROM crawled_items
            {where_sql}
            ORDER BY crawl_date DESC, created_at DESC, id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()


def query_candidates(
    db_path: str | Path = DEFAULT_DB_PATH,
    *,
    keywords: Sequence[str] | None = None,
    statuses: Sequence[str] | None = None,
    risk_levels: Sequence[str] | None = None,
    limit: int = 1_000,
) -> list[sqlite3.Row]:
    conditions: list[str] = []
    params: list[Any] = []
    for column, values in (
        ("keyword", keywords),
        ("recommendation_status", statuses),
        ("risk_level", risk_levels),
    ):
        if values:
            conditions.append(f"{column} IN ({_placeholders(values)})")
            params.extend(values)
    where_sql = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(max(1, int(limit)))
    with get_connection(db_path) as connection:
        return connection.execute(
            f"""
            SELECT id, product_name, keyword, title, price, want_count, item_url,
                   reason, risk_level, recommendation_status, created_at
            FROM product_candidates
            {where_sql}
            ORDER BY
                CASE recommendation_status
                    WHEN '可交付候选' THEN 1
                    WHEN '可观察' THEN 2
                    ELSE 3
                END,
                created_at DESC,
                id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()


def query_material_candidates(
    db_path: str | Path = DEFAULT_DB_PATH,
    *,
    limit: int = 200,
) -> list[sqlite3.Row]:
    """Return candidate products that have links and can be saved as materials."""
    with get_connection(db_path) as connection:
        return connection.execute(
            """
            SELECT id, product_name, keyword, title, price, want_count, item_url,
                   reason, risk_level, recommendation_status, created_at
            FROM product_candidates
            WHERE item_url <> ''
            ORDER BY
                CASE recommendation_status
                    WHEN '可交付候选' THEN 1
                    WHEN '可观察' THEN 2
                    ELSE 3
                END,
                CASE risk_level
                    WHEN '低' THEN 1
                    WHEN '中' THEN 2
                    ELSE 3
                END,
                COALESCE(want_count, 0) DESC,
                created_at DESC,
                id DESC
            LIMIT ?
            """,
            (max(1, int(limit)),),
        ).fetchall()


def query_student_results(
    keyword: str,
    db_path: str | Path = DEFAULT_DB_PATH,
    *,
    limit: int = 50,
) -> list[sqlite3.Row]:
    """Return learner-facing hot links for one keyword, sorted by heat proxy."""
    normalized_keyword = str(keyword or "").strip()
    if not normalized_keyword:
        return []
    with get_connection(db_path) as connection:
        return connection.execute(
            """
            SELECT id, keyword, title, price, want_count, location, seller_type,
                   item_url, image_url, crawl_date, created_at
            FROM crawled_items
            WHERE keyword = ? AND item_url <> ''
            ORDER BY
                COALESCE(want_count, -1) DESC,
                COALESCE(price, 0) DESC,
                created_at DESC,
                id DESC
            LIMIT ?
            """,
            (normalized_keyword, max(1, int(limit))),
        ).fetchall()


def is_student_result_for_keyword(row: Mapping[str, Any], keyword: str) -> bool:
    return str(row.get("keyword") or "").strip() == str(keyword or "").strip()


def _rows_to_dataframe(rows: Sequence[sqlite3.Row], pandas_module: Any) -> Any:
    return pandas_module.DataFrame([dict(row) for row in rows])


def _keyword_options(db_path: str | Path = DEFAULT_DB_PATH) -> list[str]:
    with get_connection(db_path) as connection:
        return [
            str(row[0])
            for row in connection.execute(
                "SELECT keyword FROM keywords ORDER BY priority DESC, id ASC"
            ).fetchall()
        ]


def _render_overview(st: Any, pd: Any) -> None:
    st.header("今日概览")
    summary = get_dashboard_summary()
    columns = st.columns(3)
    columns[0].metric("今日采集数量", summary["today_items"])
    columns[1].metric("启用关键词", summary["enabled_keywords"])
    columns[2].metric("今日候选品", summary["today_candidates"])

    st.subheader("最近采集")
    recent = _rows_to_dataframe(query_crawled_items(limit=10), pd)
    if recent.empty:
        st.info("还没有采集数据。先在终端运行 `python crawler.py --keyword 遮阳棚 --limit 3`。")
        return
    st.dataframe(
        recent,
        width="stretch",
        hide_index=True,
        column_config={
            "item_url": st.column_config.LinkColumn("商品链接", display_text="打开商品"),
            "image_url": st.column_config.ImageColumn("图片"),
        },
    )


def _save_one_product_from_row(
    st: Any,
    row: Mapping[str, Any],
    button_key: str,
    *,
    expected_keyword: str | None = None,
) -> None:
    if st.button("保存文案和图片", key=button_key):
        if expected_keyword and not is_student_result_for_keyword(row, expected_keyword):
            st.error(
                f"这条不是“{expected_keyword}”的结果，已拦截保存。"
                "请重新点击“开始搜索热度链接”。"
            )
            return
        try:
            with st.spinner("正在保存素材，弹出的浏览器不要关闭……"):
                message = save_product_assets_for_streamlit(
                    str(row["item_url"]),
                    str(row["title"]),
                )
            st.success(message or "已保存文案和图片。")
            folder_path = parse_saved_folder_from_message(message)
            if folder_path:
                st.session_state["last_saved_folder"] = folder_path
                st.code(folder_path)
        except Exception as exc:
            st.error(f"保存失败：{exc}")
            st.info("如果弹出浏览器要求登录或验证，请先手动完成，再点一次保存。")


def _render_manual_asset_saver(
    st: Any,
    *,
    title_hint: str = "",
    expanded: bool = True,
) -> None:
    """Stable learner flow: save assets from a pasted Xianyu item URL."""
    with st.expander("方式 1：粘贴闲鱼商品链接，直接保存素材（推荐）", expanded=expanded):
        st.write("这是最稳定的学员用法：在闲鱼里找到商品，复制链接，粘贴到这里，一键保存文案和图片。")
        item_url = st.text_input(
            "粘贴闲鱼商品链接",
            placeholder="例如：https://www.goofish.com/item?id=...",
            key="manual_item_url",
        ).strip()
        manual_title = st.text_input(
            "商品名称，可不填",
            value=title_hint,
            placeholder="不填也可以，系统会尽量从页面识别",
            key="manual_title_hint",
        ).strip()
        if st.button("保存这个链接的文案和图片", key="manual_save_asset"):
            if not item_url:
                st.warning("请先粘贴一个闲鱼商品链接。")
                return
            try:
                with st.spinner("正在打开商品详情页并保存素材，请稍等……"):
                    message = save_product_assets_for_streamlit(
                        item_url,
                        manual_title or title_hint or "商品素材",
                    )
                st.success(message or "已保存文案和图片。")
                folder_path = parse_saved_folder_from_message(message)
                if folder_path:
                    st.session_state["last_saved_folder"] = folder_path
                    st.code(folder_path)
            except Exception as exc:
                st.error(f"保存失败：{exc}")
                st.info("如果这个链接也保存失败，通常说明闲鱼详情页也要求登录/验证，需要换本地采集或人工复制方案。")


def _render_student_assistant(st: Any, pd: Any) -> None:
    st.header("闲鱼选品助手")
    st.caption("给学员的稳定流程：复制闲鱼商品链接 → 粘贴到这里 → 保存文案和图片。")

    with st.expander("给学员怎么用？点这里看", expanded=False):
        render_student_usage_help(st)

    st.info("推荐顺序：① 学员在闲鱼找商品 → ② 复制商品链接 → ③ 粘贴到这里 → ④ 保存文案和图片")
    _render_manual_asset_saver(st, expanded=True)

    st.divider()
    with st.expander("方式 2：自动搜索热度链接（试用，可能被闲鱼限制）", expanded=False):
        st.warning("自动搜索在云服务器上容易被闲鱼要求登录/验证。如果结果是 0，请直接用上面的方式 1。")
        columns = st.columns([3, 1])
        keyword = columns[0].text_input(
            "输入你想找的商品",
            value=st.session_state.get("student_keyword", ""),
            placeholder="例如：床垫、折叠桌、宠物烘干箱",
        ).strip()
        with columns[1]:
            st.write("")
            st.write("")
            limit = DEFAULT_STUDENT_LIMIT

        if st.button("开始自动搜索", type="primary", width="stretch"):
            if not keyword:
                st.warning("请先输入商品词，比如：床垫")
            else:
                st.session_state["student_keyword"] = keyword
                st.session_state["student_last_success_keyword"] = ""
                try:
                    with st.spinner("正在打开闲鱼搜索并采集前几条结果，请稍等……"):
                        item_count, candidate_count = run_student_keyword_search_for_streamlit(keyword, limit)
                    if item_count <= 0:
                        st.session_state["student_last_success_keyword"] = keyword
                        st.warning(
                            "没有抓到商品结果。一般不是商品不存在，而是闲鱼对云服务器访问要求登录、验证，"
                            "或临时限制了采集。请使用上面的方式 1 粘贴商品链接保存素材。"
                        )
                    else:
                        st.session_state["student_last_success_keyword"] = keyword
                        st.success(f"搜索完成：找到 {item_count} 条结果。")
                except Exception as exc:
                    st.error(f"搜索失败：{exc}")
                    st.info("如果浏览器要求登录或验证，请改用上面的方式 1。")
                    return

        if keyword:
            last_success_keyword = st.session_state.get("student_last_success_keyword")
            if last_success_keyword and last_success_keyword != keyword:
                st.warning(
                    f"当前输入是“{keyword}”，但最近成功搜索的是“{last_success_keyword}”。"
                    "请重新点击“开始自动搜索”。"
                )
                return

            rows = [dict(row) for row in query_student_results(keyword)]
            if not rows:
                st.info("暂时没有自动搜索结果。请优先使用上面的方式 1。")
            else:
                st.subheader(f"查看“{keyword}”的热度结果")
                st.caption("说明：闲鱼通常不直接展示真实销量，这里用“想要数”作为热度参考。")

                for index, row in enumerate(rows[:DEFAULT_STUDENT_LIMIT], start=1):
                    with st.container(border=True):
                        cols = st.columns([1, 5, 2, 2])
                        cols[0].metric("排名", index)
                        cols[1].write(row["title"])
                        cols[1].caption(f"结果关键词：{row['keyword']}")
                        cols[2].metric("想要数", row["want_count"] if row["want_count"] is not None else "空")
                        price_text = f"¥{row['price']:.2f}" if row["price"] is not None else "空"
                        cols[3].metric("价格", price_text)
                        st.link_button("打开商品链接", row["item_url"])
                        _save_one_product_from_row(
                            st,
                            row,
                            f"student_save_{row['id']}",
                            expected_keyword=keyword,
                        )

    last_saved_folder = st.session_state.get("last_saved_folder")
    if last_saved_folder:
        st.divider()
        st.subheader("刚保存的素材")
        st.write("素材文件夹：")
        st.code(str(last_saved_folder))
        if is_online_deployment():
            st.info("线上版素材保存在服务器里。管理员可在服务器目录 /opt/xianyu-data/saved_products 查看。")
        elif st.button("在访达打开素材文件夹", type="primary"):
            try:
                open_folder_for_streamlit(str(last_saved_folder))
                st.success("已打开访达。里面的“文案.txt”是文案，“images”是图片。")
            except Exception as exc:
                st.error(f"打开失败：{exc}")


def _render_cloud_login(st: Any) -> None:
    """Admin page for keeping the cloud-side Xianyu browser profile logged in."""
    st.header("云端闲鱼登录 / 验证")
    st.caption("只给管理员用。学员不需要看这个页面。")

    if not is_online_deployment():
        st.info("当前是本地版。云端登录页主要用于阿里云服务器。")

    st.warning(
        "如果学员端自动搜索一直是 0，通常不是商品不存在，"
        "而是闲鱼要求云服务器登录、扫码或安全验证。先在这里处理一次。"
    )

    screenshot_path = cloud_login_screenshot_path()
    status = cloud_login_process_status()
    status_cols = st.columns([2, 3])
    status_cols[0].metric("登录会话状态", status)
    if screenshot_path.exists():
        updated_at = time.strftime(
            "%Y-%m-%d %H:%M:%S",
            time.localtime(screenshot_path.stat().st_mtime),
        )
        status_cols[1].metric("截图更新时间", updated_at)
    else:
        status_cols[1].metric("截图更新时间", "还没有截图")

    keyword = st.text_input(
        "用于打开闲鱼的测试关键词",
        value="床垫",
        help="随便填一个常见商品词即可，只是为了打开闲鱼搜索页触发登录/验证。",
    ).strip() or "床垫"

    cols = st.columns(3)
    if cols[0].button("启动 3 分钟扫码/验证窗口", type="primary"):
        try:
            pid = start_cloud_login_session(keyword=keyword)
            st.success(f"已启动云端浏览器会话（PID {pid}）。等 5-10 秒后点“刷新二维码截图”。")
            st.rerun()
        except Exception as exc:
            st.error(f"启动失败：{exc}")

    if cols[1].button("刷新二维码截图"):
        st.rerun()

    if cols[2].button("登录后测试搜索"):
        try:
            with st.spinner("正在测试云端搜索……"):
                item_count, _ = run_student_keyword_search_for_streamlit(keyword, 5)
            if item_count > 0:
                st.success(f"测试成功：{keyword} 搜到 {item_count} 条。")
            else:
                st.warning(
                    "测试仍为 0。说明闲鱼仍在限制云服务器自动搜索，"
                    "学员端请使用“粘贴商品链接保存素材”的稳定流程。"
                )
        except Exception as exc:
            st.error(f"测试失败：{exc}")

    if screenshot_path.exists():
        st.subheader("扫码/验证截图")
        st.image(str(screenshot_path), caption="如果看到登录二维码，用手机闲鱼/淘宝扫码；如果看到验证，按页面提示完成。")
        st.info("扫码或验证完成后，等几秒钟，再点上面的“登录后测试搜索”。")
    else:
        st.info("还没有截图。请先点“启动 3 分钟扫码/验证窗口”。")

    with st.expander("管理员说明", expanded=False):
        st.write(
            "这个功能是在阿里云服务器上保存闲鱼浏览器登录状态，"
            "不需要你的 Mac 一直开着。"
        )
        st.write("但闲鱼可能仍会限制云服务器自动搜索，所以最终稳定兜底是：学员粘贴商品链接，一键保存文案和图片。")
        st.code(str(screenshot_path))


def _render_keywords(st: Any, pd: Any) -> None:
    st.header("关键词管理")
    st.caption("第一版支持启用或停用；优先级和备注可直接在 SQLite 中调整。")
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, keyword, category, enabled, priority, note, updated_at
            FROM keywords ORDER BY priority DESC, id ASC
            """
        ).fetchall()
    original = _rows_to_dataframe(rows, pd)
    original["enabled"] = original["enabled"].astype(bool)
    edited = st.data_editor(
        original,
        width="stretch",
        hide_index=True,
        disabled=["id", "keyword", "category", "priority", "note", "updated_at"],
        column_config={
            "id": None,
            "keyword": "关键词",
            "category": "分类",
            "enabled": st.column_config.CheckboxColumn("启用"),
            "priority": "优先级",
            "note": "备注",
            "updated_at": "更新时间",
        },
        key="keyword_editor",
    )
    if st.button("保存启停设置", type="primary"):
        changed = 0
        original_state = dict(zip(original["id"], original["enabled"], strict=True))
        for row in edited.to_dict("records"):
            keyword_id = int(row["id"])
            enabled = bool(row["enabled"])
            if enabled != bool(original_state[keyword_id]):
                set_keyword_enabled(keyword_id, enabled)
                changed += 1
        if changed:
            st.success(f"已保存 {changed} 个关键词的启停状态。")
            st.rerun()
        else:
            st.info("没有需要保存的变化。")


def _render_results(st: Any, pd: Any) -> None:
    st.header("采集结果")
    keyword_options = _keyword_options()
    selected_keywords = st.multiselect("关键词", keyword_options)

    price_enabled = st.checkbox("启用价格筛选")
    min_price: float | None = None
    max_price: float | None = None
    if price_enabled:
        price_columns = st.columns(2)
        min_price = float(
            price_columns[0].number_input("最低价格", min_value=0.0, value=0.0, step=10.0)
        )
        max_price = float(
            price_columns[1].number_input(
                "最高价格", min_value=0.0, value=10_000.0, step=100.0
            )
        )

    wants_enabled = st.checkbox("启用最低想要数筛选")
    min_wants = (
        int(st.number_input("最低想要数", min_value=0, value=0, step=1))
        if wants_enabled
        else None
    )
    rows = query_crawled_items(
        keywords=selected_keywords,
        min_price=min_price,
        max_price=max_price,
        min_want_count=min_wants,
    )
    data = _rows_to_dataframe(rows, pd)
    st.caption(f"共 {len(data)} 条（最多显示 1000 条）")
    if data.empty:
        st.info("当前筛选条件下没有数据。")
        return
    st.dataframe(
        data,
        width="stretch",
        hide_index=True,
        column_config={
            "item_url": st.column_config.LinkColumn("商品链接", display_text="打开商品"),
            "image_url": st.column_config.ImageColumn("图片"),
            "price": st.column_config.NumberColumn("价格", format="¥ %.2f"),
            "want_count": st.column_config.NumberColumn("想要数", format="%d"),
        },
    )


def _render_candidates(st: Any, pd: Any) -> None:
    st.header("候选品")
    st.caption("表格文字可选中后按 ⌘C 复制；商品链接可直接点击。")
    filter_columns = st.columns(3)
    selected_keywords = filter_columns[0].multiselect("关键词", _keyword_options())
    selected_statuses = filter_columns[1].multiselect(
        "推荐状态", ["可交付候选", "可观察", "不建议"]
    )
    selected_risks = filter_columns[2].multiselect("风险等级", ["低", "中", "高"])
    rows = query_candidates(
        keywords=selected_keywords,
        statuses=selected_statuses,
        risk_levels=selected_risks,
    )
    data = _rows_to_dataframe(rows, pd)
    st.caption(f"共 {len(data)} 条（最多显示 1000 条）")
    if data.empty:
        st.info("当前筛选条件下没有候选品。")
        return
    st.dataframe(
        data,
        width="stretch",
        hide_index=True,
        column_config={
            "item_url": st.column_config.LinkColumn("商品链接", display_text="打开商品"),
            "price": st.column_config.NumberColumn("价格", format="¥ %.2f"),
            "want_count": st.column_config.NumberColumn("想要数", format="%d"),
        },
    )


def _format_material_choice(row: Mapping[str, Any]) -> str:
    price = row["price"]
    wants = row["want_count"]
    price_text = f"¥{price:.0f}" if price is not None else "价格空"
    wants_text = f"{wants}想要" if wants is not None else "想要数空"
    return (
        f"{row['recommendation_status']}｜{row['keyword']}｜"
        f"{price_text}｜{wants_text}｜{row['title']}"
    )


def _render_asset_saver(st: Any, pd: Any) -> None:
    st.header("素材保存")
    st.caption("从候选品里选一条，打开详情页后自动保存商品文案和图片到本地。")

    candidates = [dict(row) for row in query_material_candidates()]
    if not candidates:
        st.info("还没有可保存素材的候选品。先采集并生成候选品。")
        return

    candidate_by_id = {int(candidate["id"]): candidate for candidate in candidates}
    selected_id = st.selectbox(
        "选择要保存的商品",
        list(candidate_by_id),
        format_func=lambda candidate_id: _format_material_choice(
            candidate_by_id[int(candidate_id)]
        ),
        index=0,
    )
    selected = candidate_by_id[int(selected_id)]
    st.write("商品链接：", selected["item_url"])
    st.write("列表标题：", selected["title"])

    if st.button("一键保存文案和图片", type="primary"):
        try:
            from asset_saver import save_product_assets

            with st.spinner("正在打开商品详情页并保存素材，浏览器弹出时不要关闭它……"):
                result = save_product_assets(
                    selected["item_url"],
                    title_hint=selected["title"],
                )
            st.success(
                f"已保存：{result['folder_path']}，图片 {result['image_count']} 张。"
            )
            st.code(str(result["folder_path"]))
        except Exception as exc:
            st.error(f"保存失败：{exc}")
            st.info("如果页面要求登录或验证，请在弹出的浏览器里完成后，再点一次保存。")

    st.subheader("已保存素材")
    saved = _rows_to_dataframe(list_saved_assets(), pd)
    if saved.empty:
        st.info("还没有保存过素材。")
        return
    st.dataframe(
        saved,
        width="stretch",
        hide_index=True,
        column_config={
            "item_url": st.column_config.LinkColumn("商品链接", display_text="打开商品"),
            "image_count": st.column_config.NumberColumn("图片数", format="%d"),
        },
    )


def main() -> None:
    try:
        import pandas as pd
        import streamlit as st
    except ImportError as exc:
        raise RuntimeError(
            "后台依赖尚未安装，请先运行 pip install -r requirements.txt"
        ) from exc

    st.set_page_config(page_title="闲鱼选品助手", page_icon="📦", layout="wide")
    init_database()
    st.title("闲鱼选品助手")
    admin_mode = st.sidebar.toggle("显示管理员功能", value=False)
    st.sidebar.caption("默认给学员使用；管理员功能请打开上方开关。")
    if is_online_deployment():
        st.sidebar.success("线上版运行中")
        st.sidebar.write("发给学员：浏览器地址栏里的公网网址")
        st.sidebar.warning("不要发 localhost，也不要发 172. 开头的内网地址。")
    else:
        st.sidebar.write("本机打开：")
        st.sidebar.code(build_lan_url("localhost"))
        st.sidebar.write("同 Wi‑Fi 临时测试：")
        st.sidebar.code(build_lan_url(get_local_lan_ip()))

    if not admin_mode:
        _render_student_assistant(st, pd)
        return

    page = st.sidebar.radio("管理员页面", PAGE_NAMES)
    st.sidebar.caption("管理员功能 · 本地 SQLite · 顺序低频采集")

    if page == "学员选品助手":
        _render_student_assistant(st, pd)
    elif page == "云端登录":
        _render_cloud_login(st)
    elif page == "今日概览":
        _render_overview(st, pd)
    elif page == "关键词管理":
        _render_keywords(st, pd)
    elif page == "采集结果":
        _render_results(st, pd)
    elif page == "候选品":
        _render_candidates(st, pd)
    else:
        _render_asset_saver(st, pd)


if __name__ == "__main__":
    main()

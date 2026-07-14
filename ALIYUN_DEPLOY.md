# 阿里云线上版说明（当前最终方案）

这版不是“同 Wi‑Fi 本地测试”，而是放在阿里云 ECS 上运行。你的 Mac 关机、没电，不影响学员打开网站。

## 给学员的地址

发给学员的是：

```text
http://你的阿里云公网IP
```

不要发：

```text
http://localhost:8501
http://172.开头的地址
```

`localhost` 和 `172.*` 都不是全国学员可用地址。

## 当前推荐用法

因为闲鱼会限制云服务器自动搜索，所以给学员的稳定流程是：

1. 学员自己在闲鱼 App 或网页里搜索商品。
2. 复制某个商品链接。
3. 回到“闲鱼选品助手”网页。
4. 粘贴商品链接。
5. 点击“保存这个链接的文案和图片”。

自动搜索仍保留，但它是试用功能：如果闲鱼要求登录、验证或风控，可能返回 0。

## 管理员要做的事

如果自动搜索一直是 0：

1. 打开网站。
2. 左侧打开“显示管理员功能”。
3. 进入“云端登录”。
4. 点击“启动 3 分钟扫码/验证窗口”。
5. 等 5–10 秒，点“刷新二维码截图”。
6. 如果截图里出现二维码或验证页，用手机扫码/验证。
7. 点“登录后测试搜索”。

这一步是在阿里云服务器上保存闲鱼浏览器状态，不要求你的 Mac 一直开着。

## 阿里云服务器更新命令

如果服务器目录本身是 Git 仓库，进入阿里云黑色终端执行：

```bash
cd /opt/xianyu-student-assistant && bash deploy/aliyun_systemd_update.sh
```

如果你不确定是不是 Git 仓库，直接用下面这个更稳的更新命令：

```bash
cd /opt && apt-get update && apt-get install -y unzip wget && rm -rf xianyu-student-assistant_new main.zip && wget -O main.zip https://github.com/zoo120/mac-mvp-1-python-2-playwright/archive/refs/heads/main.zip && unzip -q main.zip && mv mac-mvp-1-python-2-playwright-main xianyu-student-assistant_new && systemctl stop xianyu-student-assistant || true && rm -rf xianyu-student-assistant_old && mv xianyu-student-assistant xianyu-student-assistant_old || true && mv xianyu-student-assistant_new xianyu-student-assistant && cp -a xianyu-student-assistant_old/.venv xianyu-student-assistant/.venv 2>/dev/null || true && cd xianyu-student-assistant && bash deploy/aliyun_systemd_update.sh
```

这条命令不会删除 `/opt/xianyu-data`，所以数据库、素材、云端登录状态会保留。

如果只想看服务是否正常：

```bash
systemctl status xianyu-student-assistant --no-pager
```

看到：

```text
Active: active (running)
```

就是网站正在运行。

## 数据保存在哪里

服务器数据保存在：

```text
/opt/xianyu-data
```

主要目录：

- `/opt/xianyu-data/xianyu_monitor.db`：数据库
- `/opt/xianyu-data/saved_products`：保存的文案和图片
- `/opt/xianyu-data/playwright-profile`：云端闲鱼登录状态
- `/opt/xianyu-data/logs`：运行截图和日志

不要删除 `/opt/xianyu-data`。

## 重要说明

阿里云服务器是能用的，钱没有白花。它负责让全国学员访问网页。

但闲鱼搜索本身会识别云服务器、无头浏览器、异常访问，所以“自动搜索热度链接”不可能保证每次都稳定。最终版已经做了两条路：

- 能搜出来：直接看热度结果并保存素材。
- 搜不出来：学员粘贴商品链接，一键保存文案和图片。

这才是现在能稳定交付给学员的方案。

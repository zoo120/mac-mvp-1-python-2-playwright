# 闲鱼选品助手：线上部署版说明

这个版本已经整理成“可以放到云服务器”的形态。  
本地地址 `localhost:8501` 只能你自己电脑访问；全国学员要用，必须部署到公网服务器，生成一个类似 `https://xxx.com` 的网址。

## 最简单的部署方式

建议先用支持 Docker 的平台，例如 Render、Railway、Fly.io，或者一台云服务器。

项目已经包含：

- `Dockerfile`：告诉服务器怎么安装 Python、Streamlit、Playwright 浏览器。
- `render.yaml`：给 Render 使用的部署配置。
- `/data` 持久磁盘：线上数据库、登录态、保存的文案图片都会放这里，避免重启后丢失。

## 服务器需要的环境变量

默认已经写在 `Dockerfile` 里：

```bash
XIANYU_DB_PATH=/data/xianyu_monitor.db
XIANYU_SAVED_PRODUCTS_DIR=/data/saved_products
XIANYU_PROFILE_DIR=/data/playwright-profile
XIANYU_LOG_DIR=/data/logs
XIANYU_HEADLESS=1
XIANYU_NO_SANDBOX=1
```

## 很重要：线上版的限制

闲鱼搜索和商品详情页可能会要求登录、安全验证或风控。

本地版可以弹出浏览器让你手动登录；线上服务器一般没有可见浏览器窗口，所以如果闲鱼要求验证，线上采集可能会失败。  
这不是代码按钮的问题，而是闲鱼平台风控机制的问题。

第一版线上 MVP 的定位是：

1. 学员打开一个公网网址。
2. 输入商品词，比如“床垫”。
3. 系统低频搜索闲鱼。
4. 返回想要数较高的链接。
5. 点击按钮保存文案和图片。

如果后面要做成稳定商用版，建议再升级：

- 加登录账号池或人工登录后台；
- 加任务队列，避免多人同时点导致卡住；
- 加用户隔离，每个学员只能看到自己的保存记录；
- 把图片放到对象存储，而不是只放服务器硬盘。

## 本地仍然可以照常运行

双击：

```text
启动闲鱼选品助手.command
```

或者在终端运行：

```bash
.venv/bin/streamlit run app.py
```

本地运行时会继续使用可见浏览器，方便你手动登录。

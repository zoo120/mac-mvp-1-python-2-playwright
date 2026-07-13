# 阿里云 ECS 部署说明（小白版）

这份文档用于把“闲鱼选品助手”放到阿里云服务器上。部署成功后，学员可以通过一个公网 IP 或域名访问。

## 一、购买阿里云 ECS

建议配置：

- 产品：ECS 云服务器
- 地域：华东 2（上海）或华南 1（深圳）
- 系统：Ubuntu 22.04 64 位
- 规格：至少 2 核 4G
- 系统盘：40G 或以上
- 带宽：3M 起步，学员多建议 5M+
- 安全组：至少开放 `22` 和 `80` 端口

不要买太低配置。这个工具要运行 Python、Streamlit 和 Playwright 浏览器，1 核 1G 很容易失败。

## 二、连接服务器

进入阿里云控制台：

1. 打开 ECS 实例列表。
2. 找到刚买的服务器。
3. 点“远程连接”。
4. 选择 Workbench。
5. 登录系统终端。

看到黑色命令行窗口后，继续下一步。

## 三、安装 Docker

在服务器终端复制执行：

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl git docker.io docker-compose
sudo systemctl enable docker
sudo systemctl start docker
sudo docker --version
docker-compose --version
```

如果最后能看到 Docker 版本号，说明安装成功。

## 四、下载项目代码

进入 `/opt` 目录：

```bash
cd /opt
```

如果 GitHub 仓库是公开的，执行：

```bash
sudo git clone https://github.com/zoo120/mac-mvp-1-python-2-playwright.git xianyu-student-assistant
```

如果 GitHub 仓库是私有的，执行：

```bash
sudo git clone https://github.com/zoo120/mac-mvp-1-python-2-playwright.git xianyu-student-assistant
```

它会问：

```text
Username:
Password:
```

Username 填你的 GitHub 用户名。  
Password 不要填 GitHub 登录密码，要填 GitHub Personal Access Token。

如果你不知道 Token 是什么，先把仓库保持私有，告诉我当前页面，我再一步步带你创建 Token。

## 五、启动网站

进入项目目录：

```bash
cd /opt/xianyu-student-assistant
```

启动：

```bash
sudo docker-compose up -d --build
```

第一次会很慢，可能 10–30 分钟，因为要安装 Python、Playwright 和 Chromium 浏览器。

查看是否启动成功：

```bash
sudo docker-compose ps
```

如果看到 `Up` 或 `running`，说明服务启动了。

## 六、打开网站

在阿里云 ECS 实例页面找到“公网 IP”。

浏览器访问：

```text
http://你的公网IP
```

例如：

```text
http://8.130.xxx.xxx
```

能打开“闲鱼热卖品监测 MVP / 学员选品助手”页面，就成功了。

## 七、以后更新代码

进入服务器：

```bash
cd /opt/xianyu-student-assistant
git pull
sudo docker-compose up -d --build
```

## 八、保存的数据在哪里

服务器上的数据库、图片、文案会保存在：

```text
/opt/xianyu-student-assistant/server_data
```

里面会有：

- `xianyu_monitor.db`
- `saved_products/`
- `playwright-profile/`
- `logs/`

这个目录不要删除。

## 九、重要提醒

线上服务器没有你本地 Mac 那种可见浏览器窗口。闲鱼如果要求登录、验证码或安全验证，线上采集可能会失败。

第一版线上 MVP 适合先验证流程：

1. 学员打开网页。
2. 输入商品词。
3. 搜索热度链接。
4. 一键保存文案和图片。

如果要稳定给大量学员使用，后续建议升级：

- 后台账号登录管理；
- 任务队列，避免多人同时采集；
- 学员账号隔离；
- 图片云存储；
- 域名和 HTTPS。

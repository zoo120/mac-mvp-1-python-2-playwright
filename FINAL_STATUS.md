# 最终版状态

本地代码已经完成并通过验证。

## 已完成

- 学员默认进入“闲鱼选品助手”页面。
- 主流程改为“粘贴闲鱼商品链接 → 一键保存文案和图片”，适合全国学员线上使用。
- 自动搜索仍保留，但明确标记为试用功能。
- 新增管理员页面“云端登录”，用于阿里云服务器上处理闲鱼扫码/验证。
- 搜索被闲鱼登录/验证拦截时，不再误报成普通 0 结果。
- 阿里云部署说明已改成当前服务器实际使用的 systemd 方案。
- 新增阿里云更新脚本：`deploy/aliyun_systemd_update.sh`。

## 已验证

- Python 编译通过。
- Streamlit 页面无端口测试通过。
- 阿里云更新脚本语法通过。
- 单元测试通过：71 passed。

## 早上需要做的两步

### 第 1 步：把本地代码推到 GitHub

打开 GitHub Desktop：

1. 左下角 Summary 填：`final cloud learner version`
2. 点蓝色按钮 `Commit to main`
3. 点顶部 `Push origin`

### 第 2 步：更新阿里云服务器

打开阿里云黑色终端，复制执行：

```bash
cd /opt && apt-get update && apt-get install -y unzip wget && rm -rf xianyu-student-assistant_new main.zip && wget -O main.zip https://github.com/zoo120/mac-mvp-1-python-2-playwright/archive/refs/heads/main.zip && unzip -q main.zip && mv mac-mvp-1-python-2-playwright-main xianyu-student-assistant_new && systemctl stop xianyu-student-assistant || true && rm -rf xianyu-student-assistant_old && mv xianyu-student-assistant xianyu-student-assistant_old || true && mv xianyu-student-assistant_new xianyu-student-assistant && cp -a xianyu-student-assistant_old/.venv xianyu-student-assistant/.venv 2>/dev/null || true && cd xianyu-student-assistant && bash deploy/aliyun_systemd_update.sh
```

完成后看到：

```text
Active: active (running)
```

就是线上服务运行中。

## 给学员的话

发公网地址，不要发 `localhost`，不要发 `172.*`。

学员流程：

1. 在闲鱼找到商品。
2. 复制商品链接。
3. 粘贴到网页。
4. 保存文案和图片。

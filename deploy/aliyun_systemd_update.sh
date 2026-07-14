#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${1:-/opt/xianyu-student-assistant}"
DATA_DIR="${2:-/opt/xianyu-data}"
SERVICE_NAME="xianyu-student-assistant"

echo "进入项目目录：${APP_DIR}"
cd "$APP_DIR"

echo "准备 Python 虚拟环境..."
if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

echo "安装/更新 Python 依赖..."
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo "安装 Playwright 浏览器..."
.venv/bin/python -m playwright install chromium

echo "准备服务器数据目录..."
mkdir -p "${DATA_DIR}/saved_products" "${DATA_DIR}/playwright-profile" "${DATA_DIR}/logs"

echo "写入 systemd 服务..."
cat >/etc/systemd/system/${SERVICE_NAME}.service <<EOF
[Unit]
Description=Xianyu Student Assistant
After=network.target

[Service]
Type=simple
WorkingDirectory=${APP_DIR}
Environment=XIANYU_DB_PATH=${DATA_DIR}/xianyu_monitor.db
Environment=XIANYU_SAVED_PRODUCTS_DIR=${DATA_DIR}/saved_products
Environment=XIANYU_PROFILE_DIR=${DATA_DIR}/playwright-profile
Environment=XIANYU_LOG_DIR=${DATA_DIR}/logs
Environment=XIANYU_HEADLESS=1
Environment=XIANYU_NO_SANDBOX=1
ExecStart=${APP_DIR}/.venv/bin/streamlit run app.py --server.address=0.0.0.0 --server.port=80 --browser.gatherUsageStats=false
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "重启网站服务..."
systemctl daemon-reload
systemctl enable ${SERVICE_NAME}
systemctl restart ${SERVICE_NAME}

echo "当前服务状态："
systemctl status ${SERVICE_NAME} --no-pager

echo "完成。浏览器打开：http://你的公网IP"

#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${1:-/opt/xianyu-student-assistant}"

cd "$APP_DIR"

echo "开始构建并启动闲鱼选品助手..."
sudo docker compose up -d --build

echo "启动完成。"
sudo docker compose ps

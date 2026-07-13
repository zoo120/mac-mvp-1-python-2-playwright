#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${1:-/opt/xianyu-student-assistant}"

cd "$APP_DIR"

echo "拉取最新代码..."
git pull

echo "重新构建并启动..."
sudo docker compose up -d --build

echo "更新完成。"
sudo docker compose ps

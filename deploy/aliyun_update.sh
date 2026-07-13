#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${1:-/opt/xianyu-student-assistant}"

cd "$APP_DIR"

echo "拉取最新代码..."
git pull

echo "重新构建并启动..."
if command -v docker-compose >/dev/null 2>&1; then
  sudo docker-compose up -d --build
else
  sudo docker compose up -d --build
fi

echo "更新完成。"
if command -v docker-compose >/dev/null 2>&1; then
  sudo docker-compose ps
else
  sudo docker compose ps
fi

#!/usr/bin/env bash
set -euo pipefail

echo "开始安装 Docker 和常用工具..."

if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y ca-certificates curl git docker.io docker-compose-plugin
elif command -v yum >/dev/null 2>&1; then
  sudo yum install -y git yum-utils
  curl -fsSL https://get.docker.com | sudo sh
else
  echo "暂不支持当前系统。建议阿里云 ECS 使用 Ubuntu 22.04。"
  exit 1
fi

sudo systemctl enable docker
sudo systemctl start docker

echo "Docker 安装完成。"
sudo docker --version

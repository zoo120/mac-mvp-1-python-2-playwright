#!/bin/zsh
cd "$(dirname "$0")"
echo "正在启动闲鱼选品助手，请不要关闭这个窗口。"
echo ""
echo "如果浏览器没有自动打开，请手动打开："
echo "http://localhost:8501"
echo ""
.venv/bin/streamlit run app.py --server.address 0.0.0.0 --server.port 8501

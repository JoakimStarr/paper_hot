#!/bin/sh
# 单容器入口：同时启动后端(uuvicorn:8000)与前端(node:3000)
set -e

# 后端
cd /app
uvicorn app.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# 前端
cd /app/frontend
node server.js &
FRONTEND_PID=$!

# 信号转发，交给 docker 重启策略处理
trap 'kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true' TERM INT

wait

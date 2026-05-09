#!/bin/bash

echo "🛑 Stopping PaperPulse..."

# 强制关闭 8000 端口（后端）
PORT_PID=$(lsof -t -i:8000 2>/dev/null)
if [ -n "$PORT_PID" ]; then
  kill -9 $PORT_PID 2>/dev/null
  echo "Killed process on port 8000 (PID: $PORT_PID)"
else
  echo "No process found on port 8000"
fi

# 停止前端服务
pkill -f "next dev" 2>/dev/null && echo "Frontend stopped" || echo "No frontend process found"

echo ""
echo "✅ PaperPulse has been stopped"
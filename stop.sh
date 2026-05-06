#!/bin/bash

echo "🛑 Stopping PaperPulse..."

# 停止后端服务
pkill -f "uvicorn app.main:app"
echo "Backend stopped"

# 停止前端服务
pkill -f "next dev"
echo "Frontend stopped"

echo ""
echo "✅ PaperPulse has been stopped"

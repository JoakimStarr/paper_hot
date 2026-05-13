#!/bin/bash

set -e

echo "🚀 Starting ApplePaper (Development Mode)..."
echo "⚠️  DEV MODE: Hot reload enabled, not for production use"
echo ""

PROJECT_DIR="/home/joakim/Project/paper_hot"

# 启动后端服务
echo "📦 Starting backend server (dev)..."
cd "$PROJECT_DIR/backend"
source venv/bin/activate
nohup uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload > backend.log 2>&1 &
BACKEND_PID=$!
echo "   Backend started (PID: $BACKEND_PID) with hot reload"

sleep 2

# 启动前端（开发模式）
echo ""
echo "📱 Starting frontend server (dev with HMR)..."
cd "$PROJECT_DIR/frontend"
nohup npm run dev > frontend.log 2>&1 &
FRONTEND_PID=$!
echo "   Frontend started (PID: $FRONTEND_PID)"
echo "   Hot Module Replacement enabled"

sleep 3

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ ApplePaper DEV is running!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📱 Frontend:  http://localhost:3000"
echo "🔧 Backend:   http://localhost:8000"
echo "📚 API Docs:  http://localhost:8000/docs"
echo ""
echo "To stop:  ./stop.sh"
echo "Prod:     ./start.sh"
echo ""

if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "✅ Backend health check passed"
else
    echo "⚠️  Backend health check failed, check backend/backend.log"
fi
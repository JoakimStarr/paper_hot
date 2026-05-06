#!/bin/bash

echo "🚀 Starting PaperPulse..."

# 启动后端服务
echo "Starting backend server..."
cd /home/joakim/Project/paper_hot/backend
source venv/bin/activate
nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 > backend.log 2>&1 &
BACKEND_PID=$!
echo "Backend started (PID: $BACKEND_PID)"

# 等待后端启动
sleep 3

# 启动前端服务
echo "Starting frontend server..."
cd /home/joakim/Project/paper_hot/frontend
nohup npm run dev > frontend.log 2>&1 &
FRONTEND_PID=$!
echo "Frontend started (PID: $FRONTEND_PID)"

# 等待前端启动
sleep 5

echo ""
echo "✅ PaperPulse is running!"
echo ""
echo "📱 Frontend: http://localhost:3000"
echo "🔧 Backend API: http://localhost:8000"
echo "📚 API Docs: http://localhost:8000/docs"
echo ""
echo "To stop the servers:"
echo "  kill $BACKEND_PID $FRONTEND_PID"
echo ""
echo "Or run: ./stop.sh"

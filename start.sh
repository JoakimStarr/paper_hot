#!/bin/bash

set -e

# 根据脚本自身所在目录解析项目根目录（支持从任意位置调用）
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 自动定位虚拟环境（兼容 backend/venv 与项目根目录 venv）
find_venv() {
    for dir in "$PROJECT_DIR/backend/venv" "$PROJECT_DIR/venv"; do
        if [ -f "$dir/bin/activate" ]; then
            VENV_DIR="$dir"
            return 0
        fi
    done
    return 1
}

require_venv() {
    if ! find_venv; then
        echo -e "${RED}Error: 未找到虚拟环境（backend/venv 或 venv）${NC}" >&2
        exit 1
    fi
}

GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

usage() {
    echo "Usage: ./start.sh <command>"
    echo ""
    echo "Commands:"
    echo "  start      启动生产模式（默认）"
    echo "  dev        启动开发模式（热重载 / HMR）"
    echo "  stop       停止所有服务"
    echo "  restart    重启服务（生产模式）"
    echo "  status     查看服务运行状态"
    echo "  help       -h --help  显示本帮助"
    echo ""
    echo "Examples:"
    echo "  ./start.sh           # 等同 ./start.sh start"
    echo "  ./start.sh dev"
    echo "  ./start.sh restart"
}

# ───────────────────────── 停止服务 ─────────────────────────
stop_services() {
    echo "🛑 Stopping ApplePaper..."

    # 后端：占用 8000 端口的进程
    PORT_PID=$(lsof -t -i:8000 2>/dev/null || true)
    if [ -n "$PORT_PID" ]; then
        kill -9 $PORT_PID 2>/dev/null || true
        echo "   Backend stopped (PID: $PORT_PID)"
    else
        echo "   No backend process found"
    fi

    # 兜底：清理可能残留的 uvicorn 进程（如 dev 模式 --reload 子进程）
    pkill -9 -f "uvicorn app.main:app" 2>/dev/null || true

    # 前端：next 服务进程
    FRONTEND_PIDS=$(pgrep -f "next (start|dev)" 2>/dev/null || true)
    if [ -n "$FRONTEND_PIDS" ]; then
        pkill -9 -f "next (start|dev)" 2>/dev/null || true
        echo "   Frontend stopped (PID: $FRONTEND_PIDS)"
    else
        echo "   No frontend process found"
    fi

    # 兜底：占用 3000 端口的进程
    PORT3000_PID=$(lsof -t -i:3000 2>/dev/null || true)
    if [ -n "$PORT3000_PID" ]; then
        kill -9 $PORT3000_PID 2>/dev/null || true
        echo "   Stray process on port 3000 stopped (PID: $PORT3000_PID)"
    fi

    echo ""
    echo "✅ ApplePaper has been stopped"
}

# ───────────────────────── 查看状态 ─────────────────────────
status_services() {
    echo "📊 ApplePaper service status:"
    echo ""
    if lsof -t -i:8000 >/dev/null 2>&1; then
        echo -e "   Backend  (port 8000): ${GREEN}RUNNING${NC} (PID: $(lsof -t -i:8000 | tr '\n' ' '))"
    else
        echo -e "   Backend  (port 8000): ${RED}STOPPED${NC}"
    fi
    if lsof -t -i:3000 >/dev/null 2>&1; then
        echo -e "   Frontend (port 3000): ${GREEN}RUNNING${NC} (PID: $(lsof -t -i:3000 | tr '\n' ' '))"
    else
        echo -e "   Frontend (port 3000): ${RED}STOPPED${NC}"
    fi
}

# ───────────────────────── 生产模式 ─────────────────────────
start_production() {
    echo -e "🚀 Starting ApplePaper (${GREEN}Production${NC} Mode)..."
    echo ""

    load_ports
    echo "   Ports: backend=${BACKEND_PORT}, frontend=${FRONTEND_PORT}"

    # 启动后端服务
    echo "📦 Starting backend server..."
    cd "$PROJECT_DIR/backend"
    require_venv
    source "$VENV_DIR/bin/activate"
    nohup uvicorn app.main:app --host 0.0.0.0 --port "$BACKEND_PORT" > backend.log 2>&1 &
    BACKEND_PID=$!
    echo "   Backend started (PID: $BACKEND_PID)"

    # 等待后端启动
    sleep 2

    # 构建前端（生产模式）：已存在生产构建产物时跳过，可用 FORCE_BUILD=1 强制重建
    cd "$PROJECT_DIR/frontend"
    if [ -d .next/standalone ] && [ -f .next/BUILD_ID ] && [ -z "${FORCE_BUILD:-}" ]; then
        echo "   Skip build (existing .next found, set FORCE_BUILD=1 to rebuild)"
    else
        echo "🔨 Building frontend (production)..."
        # NEXT_PUBLIC_API_URL 需在构建期注入（生产包会内联该值）
        NEXT_PUBLIC_API_URL="http://localhost:${BACKEND_PORT}/api" npm run build
    fi

    # 启动前端（生产模式）
    echo ""
    echo "📱 Starting frontend server (production)..."
    nohup npm run start -- -H 0.0.0.0 -p "$FRONTEND_PORT" > frontend.log 2>&1 &
    FRONTEND_PID=$!
    echo "   Frontend started (PID: $FRONTEND_PID)"

    # 等待前端启动
    sleep 3

    print_urls "Production"
    health_check
}

# ───────────────────────── 开发模式 ─────────────────────────
start_dev() {
    echo -e "🚀 Starting ApplePaper (${YELLOW}Development${NC} Mode)..."
    echo -e "${YELLOW}⚠️  DEV MODE: Hot reload enabled, not for production use${NC}"
    echo ""

    load_ports
    echo "   Ports: backend=${BACKEND_PORT}, frontend=${FRONTEND_PORT}"

    # 启动后端服务
    echo "📦 Starting backend server (dev)..."
    cd "$PROJECT_DIR/backend"
    require_venv
    source "$VENV_DIR/bin/activate"
    nohup uvicorn app.main:app --host 0.0.0.0 --port "$BACKEND_PORT" --reload > backend.log 2>&1 &
    BACKEND_PID=$!
    echo "   Backend started (PID: $BACKEND_PID) with hot reload"

    sleep 2

    # 启动前端（开发模式）
    echo ""
    echo "📱 Starting frontend server (dev with HMR)..."
    cd "$PROJECT_DIR/frontend"
    # dev 与生产共用 .next，先清空避免与 next build 产物冲突
    rm -rf .next
    nohup npm run dev -- -H 0.0.0.0 -p "$FRONTEND_PORT" > frontend.log 2>&1 &
    FRONTEND_PID=$!
    echo "   Frontend started (PID: $FRONTEND_PID)"
    echo "   Hot Module Replacement enabled"

    sleep 3

    print_urls "DEV"
    health_check
}

# ───────────────────────── 公共输出 ─────────────────────────
# ───────── 从 backend/.env 读取端口配置（系统页可修改，重启本脚本生效） ─────────
load_ports() {
    local env_file="$PROJECT_DIR/backend/.env"
    BACKEND_PORT=$(grep -E '^backend_port=' "$env_file" 2>/dev/null | head -1 | cut -d= -f2 | tr -d ' \r')
    FRONTEND_PORT=$(grep -E '^frontend_port=' "$env_file" 2>/dev/null | head -1 | cut -d= -f2 | tr -d ' \r')
    BACKEND_PORT=${BACKEND_PORT:-8000}
    FRONTEND_PORT=${FRONTEND_PORT:-3000}
    export NEXT_PUBLIC_API_URL="http://localhost:${BACKEND_PORT}/api"
}

print_urls() {
    MODE=$1
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo -e "✅ ApplePaper ${MODE} is running!"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "📱 Frontend:  http://localhost:${FRONTEND_PORT}"
    echo "🔧 Backend:   http://localhost:${BACKEND_PORT}"
    echo "📚 API Docs:  http://localhost:${BACKEND_PORT}/docs"
    echo ""
    echo "To stop:  ./start.sh stop"
    echo "Status:   ./start.sh status"
    echo ""
}

health_check() {
    # 检查是否正常运行
    sleep 1
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo "✅ Backend health check passed"
    else
        echo "⚠️  Backend health check failed, check backend/backend.log"
    fi
}

# ───────────────────────── 命令分发 ─────────────────────────
COMMAND="${1:-start}"

case "$COMMAND" in
    start)
        start_production
        ;;
    dev)
        start_dev
        ;;
    stop)
        stop_services
        ;;
    restart)
        stop_services
        echo ""
        start_production
        ;;
    status)
        status_services
        ;;
    help|-h|--help)
        usage
        ;;
    *)
        echo -e "${RED}Unknown command: $COMMAND${NC}"
        echo ""
        usage
        exit 1
        ;;
esac

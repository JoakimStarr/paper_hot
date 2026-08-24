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

# 记录实际运行端口 / 进程的文件（stop、status 用于定位；端口被占用顺延后保存最新值）
RUNTIME_PORTS_FILE="$PROJECT_DIR/.runtime_ports"
# 端口顺延最大步数：基础端口被占用则 +1 逐级寻找空闲端口，最多顺延该步数（可按需覆盖）
PORT_MAX_TRIES=${PORT_MAX_TRIES:-100}

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
    echo ""
    echo "端口说明："
    echo "  默认后端 8000、前端 3000（backend/.env 可改）。若端口被占用，会按 +1 逐级顺延"
    echo "  找到第一个空闲端口（如 3000 被占用则尝试 3001、3002...）。前端通过 next rewrites"
    echo "  在运行时把 /api 代理到后端实际端口，因此后端端口变化无需重建前端。"
}

# ───────────────────────── 停止服务 ─────────────────────────
# 仅当进程工作目录位于本项目内时才终止（防止误杀同机其他项目的同名服务）
# 优先按进程组终止（启动时经 setsid 创建独立进程组，可连带清理 npm/next/uvicorn 子进程树）
kill_project_pids() {
    local pids="$1" name="$2"
    local pid cwd
    for pid in $pids; do
        cwd=$(readlink "/proc/$pid/cwd" 2>/dev/null) || continue
        case "$cwd" in
            "$PROJECT_DIR"/*)
                kill -9 "-$pid" 2>/dev/null || kill -9 "$pid" 2>/dev/null || true
                echo "   $name stopped (PID: $pid)"
                ;;
        esac
    done
}

stop_services() {
    echo "🛑 Stopping ApplePaper..."
    load_ports
    load_runtime_ports

    # 1) 终止上次启动记录的进程（.runtime_ports 中记录的 PID）
    if [ -f "$RUNTIME_PORTS_FILE" ]; then
        kill_project_pids "$(grep -E '^backend_pid=' "$RUNTIME_PORTS_FILE" 2>/dev/null | cut -d= -f2 | tr -d ' \r')" "Backend"
        kill_project_pids "$(grep -E '^frontend_pid=' "$RUNTIME_PORTS_FILE" 2>/dev/null | cut -d= -f2 | tr -d ' \r')" "Frontend"
    fi

    # 2) 兜底：按端口清理（同样校验属于本项目）
    kill_project_pids "$(lsof -t -i:$BACKEND_PORT 2>/dev/null || true)" "Backend(port $BACKEND_PORT)"
    kill_project_pids "$(lsof -t -i:$FRONTEND_PORT 2>/dev/null || true)" "Frontend(port $FRONTEND_PORT)"

    rm -f "$RUNTIME_PORTS_FILE"
    echo ""
    echo "✅ ApplePaper has been stopped"
}

# ───────────────────────── 查看状态 ─────────────────────────
status_services() {
    echo "📊 ApplePaper service status:"
    load_ports
    load_runtime_ports
    echo ""
    if lsof -t -i:$BACKEND_PORT >/dev/null 2>&1; then
        echo -e "   Backend  (port $BACKEND_PORT): ${GREEN}RUNNING${NC} (PID: $(lsof -t -i:$BACKEND_PORT | tr '\n' ' '))"
    else
        echo -e "   Backend  (port $BACKEND_PORT): ${RED}STOPPED${NC}"
    fi
    if lsof -t -i:$FRONTEND_PORT >/dev/null 2>&1; then
        echo -e "   Frontend (port $FRONTEND_PORT): ${GREEN}RUNNING${NC} (PID: $(lsof -t -i:$FRONTEND_PORT | tr '\n' ' '))"
    else
        echo -e "   Frontend (port $FRONTEND_PORT): ${RED}STOPPED${NC}"
    fi
}

# ───────────────────────── 生产模式 ─────────────────────────
start_production() {
    echo -e "🚀 Starting ApplePaper (${GREEN}Production${NC} Mode)..."
    echo ""

    load_ports
    resolve_ports
    echo "   Ports: backend=${BACKEND_PORT}, frontend=${FRONTEND_PORT}"

    # 启动后端服务
    echo "📦 Starting backend server..."
    cd "$PROJECT_DIR/backend"
    require_venv
    source "$VENV_DIR/bin/activate"
    setsid nohup "$VENV_DIR/bin/python" -m uvicorn app.main:app --host 0.0.0.0 --port "$BACKEND_PORT" > backend.log 2>&1 &
    BACKEND_PID=$!
    echo "backend_pid=${BACKEND_PID}" >> "$RUNTIME_PORTS_FILE"
    echo "   Backend started (PID: $BACKEND_PID)"

    # 等待后端启动
    sleep 2

    # 构建前端（生产模式）：已存在生产构建产物时跳过，可用 FORCE_BUILD=1 强制重建。
    # 端口不再在构建期内联：前端经 next rewrites 在运行时代理到后端实际地址，因此后端端口变化无需重建。
    cd "$PROJECT_DIR/frontend"
    if [ -d .next/standalone ] && [ -f .next/BUILD_ID ] && [ -z "${FORCE_BUILD:-}" ]; then
        echo "   Skip build (existing .next found, set FORCE_BUILD=1 to rebuild)"
    else
        echo "🔨 Building frontend (production)..."
        npm run build
    fi

    # 启动前端（生产模式）
    echo ""
    echo "📱 Starting frontend server (production)..."
    setsid nohup npm run start -- -H 0.0.0.0 -p "$FRONTEND_PORT" > frontend.log 2>&1 &
    FRONTEND_PID=$!
    echo "frontend_pid=${FRONTEND_PID}" >> "$RUNTIME_PORTS_FILE"
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
    resolve_ports
    echo "   Ports: backend=${BACKEND_PORT}, frontend=${FRONTEND_PORT}"

    # 启动后端服务
    echo "📦 Starting backend server (dev)..."
    cd "$PROJECT_DIR/backend"
    require_venv
    source "$VENV_DIR/bin/activate"
    setsid nohup "$VENV_DIR/bin/python" -m uvicorn app.main:app --host 0.0.0.0 --port "$BACKEND_PORT" --reload > backend.log 2>&1 &
    BACKEND_PID=$!
    echo "backend_pid=${BACKEND_PID}" >> "$RUNTIME_PORTS_FILE"
    echo "   Backend started (PID: $BACKEND_PID) with hot reload"

    sleep 2

    # 启动前端（开发模式）
    echo ""
    echo "📱 Starting frontend server (dev with HMR)..."
    cd "$PROJECT_DIR/frontend"
    # dev 与生产共用 .next，先清空避免与 next build 产物冲突
    rm -rf .next
    setsid nohup npm run dev -- -H 0.0.0.0 -p "$FRONTEND_PORT" > frontend.log 2>&1 &
    FRONTEND_PID=$!
    echo "frontend_pid=${FRONTEND_PID}" >> "$RUNTIME_PORTS_FILE"
    echo "   Frontend started (PID: $FRONTEND_PID)"
    echo "   Hot Module Replacement enabled"

    sleep 3

    print_urls "DEV"
    health_check
}

# ───────────────────────── 端口处理 ─────────────────────────
# ───────── 从 backend/.env 读取端口配置（系统页可修改，重启本脚本生效） ─────────
load_ports() {
    local env_file="$PROJECT_DIR/backend/.env"
    BACKEND_PORT=$(grep -E '^backend_port=' "$env_file" 2>/dev/null | head -1 | cut -d= -f2 | tr -d ' \r')
    FRONTEND_PORT=$(grep -E '^frontend_port=' "$env_file" 2>/dev/null | head -1 | cut -d= -f2 | tr -d ' \r')
    BACKEND_PORT=${BACKEND_PORT:-8000}
    FRONTEND_PORT=${FRONTEND_PORT:-3000}
}

# ───────── 仅 stop/status 使用：采用上次实际运行端口（仅当该端口确有进程监听时才采信） ─────────
load_runtime_ports() {
    [ -f "$RUNTIME_PORTS_FILE" ] || return 0
    local rb rf
    rb=$(grep -E '^backend_port=' "$RUNTIME_PORTS_FILE" 2>/dev/null | head -1 | cut -d= -f2 | tr -d ' \r')
    rf=$(grep -E '^frontend_port=' "$RUNTIME_PORTS_FILE" 2>/dev/null | head -1 | cut -d= -f2 | tr -d ' \r')
    if [ -n "$rb" ] && port_in_use "$rb"; then
        BACKEND_PORT=$rb
    fi
    if [ -n "$rf" ] && port_in_use "$rf"; then
        FRONTEND_PORT=$rf
    fi
}

# 判定端口当前是否有进程监听
port_in_use() {
    lsof -t -i:"$1" >/dev/null 2>&1
}

# 从基础端口开始 +1 +1 递增，返回第一个空闲端口（可预期、有规律，替代随机分配）
next_free_port() {
    local base="$1" name="$2"
    local port="$base"
    local n="${PORT_MAX_TRIES:-100}"
    local i=0
    while port_in_use "$port"; do
        port=$((port + 1))
        i=$((i + 1))
        if [ "$i" -ge "$n" ]; then
            echo -e "${RED}Error: ${name} 从端口 ${base} 顺延 ${n} 次后仍未找到空闲端口${NC}" >&2
            return 1
        fi
    done
    if [ "$port" -ne "$base" ]; then
        echo -e "${YELLOW}⚠️  ${name} 端口 ${base} 已被占用，顺延使用空闲端口 ${port}${NC}" >&2
    fi
    echo "$port"
    return 0
}

# 仅用于启动流程：按顺序解析实际可用端口，并导出前端运行时所需的后端地址
resolve_ports() {
    BACKEND_PORT=$(next_free_port "$BACKEND_PORT" "backend") || exit 1
    FRONTEND_PORT=$(next_free_port "$FRONTEND_PORT" "frontend") || exit 1
    # 前端通过 next rewrites 在运行时把 /api 代理到后端，仅需注入后端实际地址，无需构建期内联
    export BACKEND_API_URL="http://localhost:${BACKEND_PORT}"
    # 记录实际端口，供本次启动后的 stop / status 使用
    cat > "$RUNTIME_PORTS_FILE" <<EOF
backend_port=${BACKEND_PORT}
frontend_port=${FRONTEND_PORT}
EOF
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
    if curl -s http://localhost:${BACKEND_PORT}/health > /dev/null 2>&1; then
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
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

# 记录实际运行端口 / 进程 / 启动模式的文件（stop、status、restart 用于定位；端口被占用顺延后保存最新值）
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
    echo "  restart    重启服务（默认沿用上次启动模式；可用 restart dev / restart prod 显式指定）"
    echo "  status     查看服务运行状态"
    echo "  help       -h --help  显示本帮助"
    echo ""
    echo "Examples:"
    echo "  ./start.sh           # 等同 ./start.sh start"
    echo "  ./start.sh dev"
    echo "  ./start.sh restart   # 沿用上次模式重启"
    echo "  ./start.sh restart dev"
    echo ""
    echo "端口说明："
    echo "  默认后端 8000、前端 3000（backend/.env 可改）。若端口被占用，启动时会先展示"
    echo "  占用进程并询问处理方式：[k] kill 占用进程继续使用，[n] 顺延 +1 使用新端口"
    echo "  （3000 被占用则尝试 3001、3002...），[q] 退出。可用 PORT_CONFLICT=kill|shift"
    echo "  预置选择（非交互环境默认自动顺延）。前端通过 next rewrites 在运行时把 /api"
    echo "  代理到后端实际端口，因此后端端口变化无需重建前端。"
    echo ""
    echo "其他说明："
    echo "  - 启动前若检测到本项目的旧实例仍在运行，会先自动停止，避免双实例并存。"
    echo "  - dev 模式启动时会清空 .next（依赖或导入结构变更后旧产物会导致"
    echo "    Loading CSS chunk failed 等前端报错）。"
    echo "  - 健康检查为轮询等待（后端 30s / 前端 60s），替代旧的固定 sleep。"
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

# ───────── 启动前自动清理本项目的旧实例 ─────────
# 背景：旧实例未停时再次 start 会端口顺延另起新进程，导致双实例并存、
# 浏览器连到陈旧的 dev server（典型症状：Loading CSS chunk ... failed）。
# 仅清理「记录在案且确实存活且工作目录属于本项目」的进程；记录的进程均已退出时只清掉过期记录。
stop_stale_instance() {
    [ -f "$RUNTIME_PORTS_FILE" ] || return 0
    local bp fp pid alive=""
    bp=$(grep -E '^backend_pid=' "$RUNTIME_PORTS_FILE" 2>/dev/null | head -1 | cut -d= -f2 | tr -d ' \r')
    fp=$(grep -E '^frontend_pid=' "$RUNTIME_PORTS_FILE" 2>/dev/null | head -1 | cut -d= -f2 | tr -d ' \r')
    for pid in $bp $fp; do
        kill -0 "$pid" 2>/dev/null && alive="$alive $pid"
    done
    if [ -z "$alive" ]; then
        # 记录的进程均已退出：仅清理过期记录
        rm -f "$RUNTIME_PORTS_FILE"
        return 0
    fi
    echo -e "${YELLOW}♻️  检测到本项目的旧实例仍在运行 (PID:${alive})，先自动停止以避免双实例${NC}"
    kill_project_pids "$bp" "Backend(stale)"
    kill_project_pids "$fp" "Frontend(stale)"
    rm -f "$RUNTIME_PORTS_FILE"
    sleep 1
}

# ───────────────────────── 查看状态 ─────────────────────────
status_services() {
    echo "📊 ApplePaper service status:"
    load_ports
    load_runtime_ports
    local mode
    mode=$(grep -E '^mode=' "$RUNTIME_PORTS_FILE" 2>/dev/null | head -1 | cut -d= -f2 | tr -d ' \r')
    mode=${mode:-unknown}
    echo "   Last start mode: ${mode}"
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

    stop_stale_instance
    load_ports
    resolve_ports prod
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

    # 等后端健康后再启前端：避免前端先就绪、浏览器打开即吃到代理 500（socket hang up）
    wait_for_http "http://localhost:${BACKEND_PORT}/health" "Backend" "backend/backend.log" 30 || true

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

    print_urls "Production"
    health_check
}

# ───────────────────────── 开发模式 ─────────────────────────
start_dev() {
    echo -e "🚀 Starting ApplePaper (${YELLOW}Development${NC} Mode)..."
    echo -e "${YELLOW}⚠️  DEV MODE: Hot reload enabled, not for production use${NC}"
    echo ""

    stop_stale_instance
    load_ports
    resolve_ports dev
    echo "   Ports: backend=${BACKEND_PORT}, frontend=${FRONTEND_PORT}"

    # 启动后端服务
    # 注意：WSL 环境下 uvicorn --reload 的 spawn 子进程存在 loopback SYN 不应答问题
    # （端口在监听但 TCP 握手挂起），故 dev 模式也用无 reload 启动；改后端代码后需 restart
    echo "📦 Starting backend server (dev, no reload)..."
    cd "$PROJECT_DIR/backend"
    require_venv
    source "$VENV_DIR/bin/activate"
    setsid nohup "$VENV_DIR/bin/python" -m uvicorn app.main:app --host 0.0.0.0 --port "$BACKEND_PORT" > backend.log 2>&1 &
    BACKEND_PID=$!
    echo "backend_pid=${BACKEND_PID}" >> "$RUNTIME_PORTS_FILE"
    echo "   Backend started (PID: $BACKEND_PID) without hot reload"

    # 等后端健康后再启前端：避免前端先就绪、浏览器打开即吃到代理 500（socket hang up）
    wait_for_http "http://localhost:${BACKEND_PORT}/health" "Backend" "backend/backend.log" 30 || true

    # 启动前端（开发模式）
    echo ""
    echo "📱 Starting frontend server (dev with HMR)..."
    cd "$PROJECT_DIR/frontend"
    # dev 与生产共用 .next；依赖或导入结构变更后，旧产物会导致浏览器端
    # 「Loading CSS chunk ... failed」等问题，启动前一律清空重建
    rm -rf .next
    setsid nohup npm run dev -- -H 0.0.0.0 -p "$FRONTEND_PORT" > frontend.log 2>&1 &
    FRONTEND_PID=$!
    echo "frontend_pid=${FRONTEND_PID}" >> "$RUNTIME_PORTS_FILE"
    echo "   Frontend started (PID: $FRONTEND_PID)"
    echo "   Hot Module Replacement enabled"

    print_urls "DEV"
    health_check
}

# ───────────────────────── 重启服务 ─────────────────────────
# 默认沿用上次启动模式（.runtime_ports 中的 mode= 记录，缺省 prod）；
# 也可显式指定：./start.sh restart dev | ./start.sh restart prod
restart_services() {
    local target="${1:-}"
    if [ -z "$target" ]; then
        target=$(grep -E '^mode=' "$RUNTIME_PORTS_FILE" 2>/dev/null | head -1 | cut -d= -f2 | tr -d ' \r')
        target=${target:-prod}
    fi
    stop_services
    echo ""
    if [ "$target" = "dev" ]; then
        start_dev
    else
        start_production
    fi
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

# 交互式处理端口冲突：让用户决定 kill 占用进程、顺延新端口或退出
# 返回值：0 = 端口已释放可继续使用；1 = 放弃启动；2 = 顺延下一个端口
# 可用 PORT_CONFLICT=kill|shift 预置选择；无终端（非交互环境）时默认顺延
handle_port_conflict() {
    local port="$1" name="$2"
    local choice pid_list pid_display
    local conflict_mode="${PORT_CONFLICT:-ask}"

    # 每行一个 PID（不转成空格分隔，避免 zsh/bash 对未加引号变量分词行为不一致）
    pid_list=$(lsof -t -i:"$port" 2>/dev/null)
    pid_display=$(echo "$pid_list" | tr '\n' ' ')

    echo "" >&2
    echo -e "${YELLOW}⚠️  ${name} 端口 ${port} 已被占用${NC}" >&2
    lsof -i:"$port" 2>/dev/null | tail -n +2 | sed 's/^/     /' >&2

    case "$conflict_mode" in
        kill)
            choice="k" ;;
        shift|new)
            choice="n" ;;
        *)
            if [ ! -t 0 ]; then
                echo -e "${YELLOW}   非交互环境（无终端），默认顺延新端口；可用 PORT_CONFLICT=kill|shift 预设行为${NC}" >&2
                choice="n"
            else
                while true; do
                    echo "" >&2
                    echo "   请选择处理方式：" >&2
                    echo "     [k] kill 占用进程，继续使用该端口" >&2
                    echo "     [n] 顺延使用新端口（+1 递增）" >&2
                    echo "     [q] 退出启动" >&2
                    read -r -p "   请输入 [k/n/q]: " choice
                    case "$choice" in
                        [kKnNqQ]) break ;;
                        *) echo -e "${RED}   无效输入，请输入 k / n / q${NC}" >&2 ;;
                    esac
                done
                choice=$(echo "$choice" | tr 'A-Z' 'a-z')
            fi
            ;;
    esac

    case "$choice" in
        k)
            echo -e "   Killing process(es) on port $port: ${pid_display:-无}" >&2
            # 先优雅终止，未成功再强制
            for pid in $pid_list; do
                kill "$pid" 2>/dev/null || true
            done
            sleep 1
            for pid in $pid_list; do
                if kill -0 "$pid" 2>/dev/null; then
                    kill -9 "$pid" 2>/dev/null || true
                fi
            done
            if port_in_use "$port"; then
                echo -e "${RED}Error: ${name} 端口 ${port} 的占用进程无法终止${NC}" >&2
                return 1
            fi
            echo -e "${GREEN}   端口 ${port} 已释放${NC}" >&2
            return 0
            ;;
        n)
            return 2
            ;;
        q)
            echo -e "${RED}Aborted by user${NC}" >&2
            return 1
            ;;
    esac
}

# 从基础端口开始 +1 +1 递增，返回第一个空闲端口（可预期、有规律，替代随机分配）
# 基础端口被占用时优先询问用户（见 handle_port_conflict），之后顺延过程保持静默递增
next_free_port() {
    local base="$1" name="$2"
    local port="$base"
    local n="${PORT_MAX_TRIES:-100}"
    local i=0
    while port_in_use "$port"; do
        if [ "$port" -eq "$base" ]; then
            handle_port_conflict "$port" "$name"
            local rc=$?
            [ "$rc" -eq 1 ] && return 1
            if [ "$rc" -eq 2 ]; then
                port=$((port + 1))
                i=$((i + 1))
            fi
            continue
        fi
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
# mode 参数（dev|prod）写入 .runtime_ports，供 restart 沿用上次模式
resolve_ports() {
    local mode="${1:-prod}"
    BACKEND_PORT=$(next_free_port "$BACKEND_PORT" "backend") || exit 1
    FRONTEND_PORT=$(next_free_port "$FRONTEND_PORT" "frontend") || exit 1
    # 前端通过 next rewrites 在运行时把 /api 代理到后端，仅需注入后端实际地址，无需构建期内联
    export BACKEND_API_URL="http://localhost:${BACKEND_PORT}"
    # 记录实际端口与模式，供本次启动后的 stop / status / restart 使用
    cat > "$RUNTIME_PORTS_FILE" <<EOF
mode=${mode}
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

# ───────── 就绪等待（轮询重试，替代固定 sleep） ─────────
# dev 首次编译、后端 reload 都可能超过固定等待时长；轮询直至就绪或超时。
# 返回 0 = 就绪；1 = 超时（调用方用 || true 兜底，不影响 set -e）
wait_for_http() {
    local url="$1" name="$2" log_hint="$3" tries="${4:-30}"
    local i=0
    while [ "$i" -lt "$tries" ]; do
        if curl -sf --max-time 5 -o /dev/null "$url" 2>/dev/null; then
            echo -e "${GREEN}✅ ${name} 就绪 (${url})${NC}"
            return 0
        fi
        i=$((i + 1))
        sleep 1
    done
    echo -e "${RED}⚠️  ${name} 在 ${tries}s 内未就绪（${url}），请检查 ${log_hint}${NC}"
    return 1
}

# 健康检查：后端 /health + 前端首页，均带重试等待
health_check() {
    wait_for_http "http://localhost:${BACKEND_PORT}/health" "Backend" "backend/backend.log" 30 || true
    wait_for_http "http://localhost:${FRONTEND_PORT}" "Frontend" "frontend/frontend.log" 60 || true
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
        restart_services "${2:-}"
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

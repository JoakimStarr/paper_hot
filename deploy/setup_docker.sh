#!/bin/bash
# ============================================================
# 阿里云轻量服务器 Docker 部署脚本（首次部署 / 迁移用）
#
# 用法（在服务器上，仓库 clone 到的目录内执行）：
#   sudo bash deploy/setup_docker.sh
#
# 作用：
#   1. 安装 Docker 与 compose 插件（Ubuntu 22.04）
#   2. 备份并迁移现有裸机数据库到 compose 挂载目录 backend/data/
#   3. 拉取镜像并启动容器（backend 512M / frontend 256M）
#
# 前提：
#   - 服务器系统为 Ubuntu 22.04（其他版本请调整安装命令）
#   - 已在 GitHub 仓库配置 Secrets：ALIYUN_REGISTRY_USERNAME / ALIYUN_REGISTRY_PASSWORD
#   - CI 已成功推送过镜像到阿里云仓库
# ============================================================

set -e

# ---- 可配置项 ----
# 现有裸机部署的 sqlite 数据库绝对路径（用 find / -name paperpulse.db 定位后修改）
DB_SOURCE="${DB_SOURCE:-/home/ubuntu/paper_hot/backend/data/paperpulse.db}"
# 是否在启动 docker 前停止旧裸机服务（start.sh 管理的服务）
STOP_LEGACY="${STOP_LEGACY:-yes}"

GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo -e "${YELLOW}=== 1/4 安装 Docker 与 compose 插件 ===${NC}"
if ! command -v docker >/dev/null 2>&1; then
    curl -fsSL https://get.docker.com | sh
    sudo systemctl enable --now docker
else
    echo "docker 已安装：$(docker --version)"
fi
if ! docker compose version >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y docker-compose-plugin
fi

echo -e "${YELLOW}=== 2/4 停止旧裸机服务（释放 3000/8000 端口）===${NC}"
if [ "$STOP_LEGACY" = "yes" ] && [ -f "$PROJECT_DIR/start.sh" ]; then
    # 兼容 start.sh 管理的旧部署；若旧服务不是本项目 start.sh 起的，请手动 stop
    bash "$PROJECT_DIR/start.sh" stop 2>/dev/null || echo "（无 start.sh 托管的服务或已停止）"
fi
# 兜底：按端口清理占用（谨慎，仅当确认是旧服务的进程）
# sudo fuser -k 3000/tcp 2>/dev/null || true
# sudo fuser -k 8000/tcp 2>/dev/null || true

echo -e "${YELLOW}=== 3/4 备份并迁移现有数据库 ===${NC}"
DB_DIR="$PROJECT_DIR/backend/data"
mkdir -p "$DB_DIR"
# 首次迁移：若挂载目录尚无数据库，且能找到旧库，则复制过去（保留原文件）
if [ ! -f "$DB_DIR/paperpulse.db" ]; then
    if [ -f "$DB_SOURCE" ]; then
        cp -v "$DB_SOURCE" "$DB_DIR/paperpulse.db"
        echo -e "${GREEN}数据库已从 $DB_SOURCE 复制到 $DB_DIR/paperpulse.db${NC}"
    else
        echo -e "${RED}未找到旧数据库 $DB_SOURCE，将以空库启动。${NC}"
        echo -e "${YELLOW}若数据库在其它路径，请修改脚本顶部 DB_SOURCE 后重跑。${NC}"
    fi
else
    echo "挂载目录已有数据库，跳过迁移（避免覆盖新数据）"
fi
# 备份（每次启动前留档，防误操作）
if [ -f "$DB_DIR/paperpulse.db" ]; then
    cp -v "$DB_DIR/paperpulse.db" "$DB_DIR/paperpulse.db.bak.$(date +%Y%m%d%H%M%S)" || true
fi

echo -e "${YELLOW}=== 4/4 拉取镜像并启动容器 ===${NC}"
docker compose pull
docker compose up -d

echo ""
echo -e "${GREEN}部署完成！${NC}"
echo "  前端: http://<服务器公网IP>:3000"
echo "  后端: http://<服务器公网IP>:8000/health"
echo ""
echo "常用命令："
echo "  查看状态    docker compose ps"
echo "  查看日志    docker compose logs -f backend / frontend"
echo "  更新部署    docker compose pull && docker compose up -d"
echo "  停止服务    docker compose down"

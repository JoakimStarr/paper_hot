#!/bin/bash

# PaperPulse 一键安装脚本
# 用法:
#   ./install.sh                  # 基础安装（venv + 服务端依赖），交互询问是否装本地向量模型
#   ./install.sh --with-ollama    # 基础安装 + Ollama 本地向量模型（bge-m3，国内加速下载）
#   ./install.sh --base-only      # 仅基础安装，不询问
#   ./install.sh --model nomic-embed-text   # 指定 embedding 模型

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

GREEN='\033[0;32m'; YELLOW='\033[0;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'
info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
fail()  { echo -e "${RED}[FAIL]${NC} $1" >&2; exit 1; }

# ---------- 参数解析 ----------
WITH_OLLAMA=""; BASE_ONLY=""; MODEL_NAME="bge-m3"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --with-ollama) WITH_OLLAMA="yes" ;;
        --base-only)   BASE_ONLY="yes" ;;
        --model)       MODEL_NAME="$2"; shift ;;
        -h|--help)     grep '^#' "$0" | head -7 | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) fail "未知参数: $1（-h 查看帮助）" ;;
    esac
    shift
done

# ---------- 1. Python 虚拟环境 ----------
PY=${PYTHON:-python3}
VNUM=$($PY -c 'import sys;print("%d.%d"%sys.version_info[:2])')
info "Python 版本: $VNUM"
$PY -c 'import sys; exit(0 if sys.version_info >= (3,11) else 1)' || fail "需要 Python 3.11+"

if [ ! -f venv/bin/activate ]; then
    info "创建虚拟环境 venv/"
    $PY -m venv venv || fail "venv 创建失败（Debian/Ubuntu 需先: apt install python3-venv）"
fi
ok "虚拟环境就绪"

info "安装服务端依赖（requirements.txt，不含爬虫库）"
# 用 python -m pip 而非 pip 入口脚本：后者 shebang 硬编码创建时路径，venv 目录被改名/移动后会失效
venv/bin/python -m pip install -q --upgrade pip
venv/bin/python -m pip install -q -r requirements.txt || fail "依赖安装失败"
ok "依赖安装完成"

# ---------- 2. .env ----------
if [ ! -f backend/.env ]; then
    cp backend/.env.example backend/.env
    warn "已从模板生成 backend/.env —— 云端 AI 至少配置一个 Key（ZHIPU_API_KEY 等），否则仅爬虫/浏览功能可用"
fi

# ---------- 3. Ollama 本地向量模型 ----------
ask_ollama() {
    [[ "$BASE_ONLY" == "yes" ]] && return 1
    [[ "$WITH_OLLAMA" == "yes" ]] && return 0
    if [ -t 0 ]; then
        read -rp "$(echo -e "${BLUE}是否安装本地向量模型（Ollama + $MODEL_NAME）？数据不出本机、零API成本 [y/N]${NC} ")" a
        [[ "$a" =~ ^[Yy]$ ]]
    else
        return 1
    fi
}

if ! ask_ollama; then
    ok "跳过 Ollama。后续可随时运行 ./install.sh --with-ollama 补装"
    echo ""
    info "下一步: 编辑 backend/.env 配置 AI Key，然后 ./start.sh"
    exit 0
fi

OLLAMA_URL="http://localhost:11434"
# bge-m3 官方库 FP16 blob 摘要（魔搭 gpustack/bge-m3-GGUF 的 FP16 文件与官方字节一致，可预置秒过校验）
BGE_M3_BLOB="sha256-daec91ffb5dd0c27411bd71f29932917c49cf529a641d0168496c3a501e3062c"
BGE_M3_GGUF_URL="https://modelscope.cn/models/gpustack/bge-m3-GGUF/resolve/master/bge-m3-FP16.gguf"

api_alive() { curl -s --max-time 3 "$OLLAMA_URL/api/version" | grep -q version; }

ensure_daemon() {
    api_alive && { ok "Ollama 服务已在运行"; return 0; }
    info "启动 Ollama 服务"
    systemctl start ollama 2>/dev/null && sleep 2 || true
    api_alive && return 0
    # systemd 不可用（如 WSL）：前台守护方式拉起
    mkdir -p ~/.ollama
    nohup ollama serve >/dev/null 2>&1 &
    sleep 2
    api_alive || fail "Ollama 服务启动失败，请手动运行 ollama serve 后重试"
}

runtime_ok() {
    # 功能级探测：能返回 embeddings 才算运行时完整（残缺安装会报 llama-server not found）
    curl -s --max-time 60 "$OLLAMA_URL/api/embed" \
        -d "{\"model\":\"$MODEL_NAME\",\"input\":\"ping\"}" | grep -q '"embeddings"'
}

install_ollama_runtime() {
    warn "Ollama 运行时缺失或残缺（仅有客户端二进制），开始完整安装"
    curl -fsSL https://ollama.com/install.sh | sh || fail "Ollama 安装失败"
    command -v ollama >/dev/null || fail "ollama 未找到"
}

ensure_model() {
    # ollama list 显示名带 :latest 等 tag 后缀，归一化后比对
    if ollama list 2>/dev/null | awk 'NR>1{print $1}' | sed 's/:[^:]*$//' | grep -qx "$MODEL_NAME"; then
        return 0
    fi
    info "拉取模型 $MODEL_NAME（国内加速：魔搭优先）"

    if [ "$MODEL_NAME" = "bge-m3" ]; then
        # 路径A：魔搭 OCI 直拉（简单；latest 标签为量化版，追求检索极致质量见 README 方式二 FP16）
        if ollama pull modelscope.cn/gpustack/bge-m3-GGUF; then
            ollama cp modelscope.cn/gpustack/bge-m3-GGUF bge-m3
            return 0
        fi
        warn "OCI 直拉失败，切换为直下 GGUF + 导入（支持断点续传）"
        # 路径B：直下 FP16 + blob 预置（实测国内最快且可续传）
        local gguf="$HOME/.ollama/import/bge-m3-FP16.gguf"
        mkdir -p "$HOME/.ollama/import"
        curl -fL -C - -o "$gguf" "$BGE_M3_GGUF_URL" || fail "GGUF 下载失败（重跑本命令可续传）"
        if ollama create bge-m3 -f <(printf 'FROM %s\nPARAMETER num_ctx 8192\n' "$gguf") 2>/dev/null; then
            return 0
        fi
        # create 缺 llama-quantize 时：blob 预置 + pull 秒级完成（文件与官方库字节一致）
        warn "create 校验不可用，改用 blob 预置法"
        mkdir -p ~/.ollama/models/blobs
        cp "$gguf" ~/.ollama/models/blobs/$BGE_M3_BLOB
        ollama pull bge-m3
    else
        ollama pull "$MODEL_NAME"
    fi
}

update_env_for_ollama() {
    # 合并而非覆盖：保留已有 custom_providers（如阿里云百炼），upsert ollama 条目
    venv/bin/python - "$MODEL_NAME" <<'EOF'
import json, sys, pathlib
model = sys.argv[1]
env = pathlib.Path("backend/.env")
lines = env.read_text(encoding="utf-8").splitlines()

def upsert(lines, key, value):
    out, found = [], False
    for l in lines:
        if l.split("=", 1)[0].strip().lower() == key.lower():
            out.append(f"{key}={value}"); found = True
        elif l.strip():
            out.append(l)
    return out + ([] if found else [f"{key}={value}"])

providers = []
for l in lines:
    if l.startswith("custom_providers="):
        try: providers = json.loads(l.split("=", 1)[1])
        except Exception: providers = []
providers = [p for p in providers if p.get("name") != "ollama"]
providers.append({"name": "ollama", "base_url": "http://localhost:11434/v1",
                  "api_key": "ollama", "models": [model]})

lines = upsert(lines, "custom_providers",
               json.dumps(providers, ensure_ascii=False))
lines = upsert(lines, "embedding_model", f"ollama/{model}")
env.write_text("\n".join(lines) + "\n", encoding="utf-8")
print(f"embedding_model -> ollama/{model}")
EOF
}

# ---------- 执行 ----------
command -v ollama >/dev/null || install_ollama_runtime
ensure_daemon

# 运行时完整性探测：无模型时 embed 报错属预期，但报 llama-server 则必须重装
probe=$(curl -s --max-time 30 "$OLLAMA_URL/api/embed" -d '{"input":"ping"}' || true)
if echo "$probe" | grep -q "llama-server binary not found"; then
    install_ollama_runtime
    pkill -f "ollama serve" 2>/dev/null || true
    systemctl restart ollama 2>/dev/null || { nohup ollama serve >/dev/null 2>&1 & sleep 2; }
    ensure_daemon
fi

ensure_model
info "验证向量化接口（首次调用需加载模型，CPU 数秒）..."
runtime_ok || fail "embedding 探测失败：ollama 运行时不完整或模型异常"
ok "向量化接口正常"

update_env_for_ollama

cat <<EOF

$(printf "${GREEN}✔ 安装完成${NC}")
  - 向量模型: $MODEL_NAME（本地推理）
  - 已写入 backend/.env（custom_providers 合并，原有 provider 保留）

下一步:
  1. ./start.sh 启动服务
  2. 若库里已有其他模型的旧向量，执行全量重建（见 README_CN.md「本地向量模型」第4节）:
     curl -X POST "http://localhost:8000/api/topic-validator/embeddings/backfill"
EOF

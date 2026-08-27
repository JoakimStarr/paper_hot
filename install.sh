#!/bin/bash

# PaperPulse 自适应安装脚本
# 用法:
#   ./install.sh                  # 基础安装（venv + 服务端依赖），交互询问是否装本地向量模型
#   ./install.sh --with-ollama    # 基础安装 + Ollama 本地向量模型（bge-m3，国内加速下载）
#   ./install.sh --base-only      # 仅基础安装，不询问
#   ./install.sh --force          # 强制重装依赖并重新探测 Ollama（跳过“已就绪”捷径）
#   ./install.sh --model nomic-embed-text   # 指定 embedding 模型
#   ./install.sh --python python3.12        # 指定 Python 解释器（默认自动挑选 3.9+）
#
# 自适应特性：重复运行会逐步骤检测「已完成项」并跳过——
#   - Python 自动挑选系统可用的 3.9+，不硬性要求 3.11，旧版本降级为警告交予 pip 处理
#   - venv 已存在且可用则跳过创建（损坏时自动重建）
#   - 依赖按 requirements 哈希 + 关键包导入检测，未变化则跳过安装
#   - faiss-cpu 为可选加速依赖（选题验证向量召回），脚本尽力安装，失败自动降级 numpy
#   - backend/.env 已存在则跳过生成
#   - Ollama 运行时/守护进程/模型均已就绪则整体跳过，仅刷新 .env

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

GREEN='\033[0;32m'; YELLOW='\033[0;33m'; RED='\033[0;31m'; BLUE='\033[0;34m'; NC='\033[0m'
info()  { echo -e "${BLUE}[INFO]${NC} $1"; }
ok()    { echo -e "${GREEN}[OK]${NC} $1"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $1"; }
fail()  { echo -e "${RED}[FAIL]${NC} $1" >&2; exit 1; }

command_exists() { command -v "$1" >/dev/null 2>&1; }

# ---------- 参数解析 ----------
WITH_OLLAMA=""; BASE_ONLY=""; FORCE=""; MODEL_NAME="bge-m3"
while [[ $# -gt 0 ]]; do
    case "$1" in
        --with-ollama) WITH_OLLAMA="yes" ;;
        --base-only)   BASE_ONLY="yes" ;;
        --force)       FORCE="yes" ;;
        --model)       MODEL_NAME="$2"; shift ;;
        --python)      PYTHON="$2"; shift ;;
        -h|--help)     grep '^# ' "$0" | head -9 | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) fail "未知参数: $1（-h 查看帮助）" ;;
    esac
    shift
done

# ---------- 1. Python 虚拟环境 ----------
# 自动挑选系统可用的 Python 3.9+；旧版本只警告不阻断，能否安装交给 pip 自适应
pick_python() {
    local p cands=()
    for p in python3.14 python3.13 python3.12 python3.11 python3.10 python3.9 python3; do
        command_exists "$p" && cands+=("$p")
    done
    for p in "${cands[@]}"; do
        if "$p" -c 'import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)' 2>/dev/null; then
            echo "$p"; return 0
        fi
    done
    # 全都不足 3.9 时回退到任意可运行的 python3，交由下方警告 + pip 兜底
    for p in "${cands[@]}"; do
        if "$p" -c 'import sys' 2>/dev/null; then echo "$p"; return 0; fi
    done
    return 1
}

if [ -n "${PYTHON:-}" ]; then
    PY="$PYTHON"
    "$PY" -c 'import sys' 2>/dev/null || fail "指定的 Python 不可用: $PY"
else
    PY="$(pick_python || true)"
    [ -n "$PY" ] || fail "未找到 Python，请先安装 python3（Debian/Ubuntu: apt install python3 python3-venv）"
fi

VNUM="$("$PY" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null || echo "?")"
info "使用 Python: $PY (版本 $VNUM)"

if "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else 1)' 2>/dev/null; then
    :
elif "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)' 2>/dev/null; then
    warn "Python $VNUM 低于建议的 3.11+：pip 会自动选择兼容版本的依赖，个别包若失败请升级 Python"
else
    warn "Python $VNUM 过旧（<3.9）：多数依赖最新版无法安装，强烈建议改用 Python 3.11+"
fi

if [ -f venv/bin/activate ] && venv/bin/python -m pip --version >/dev/null 2>&1; then
    ok "虚拟环境已存在且可用，跳过创建"
else
    if [ -d venv ]; then
        warn "venv/ 存在但已损坏，重建（旧依赖将被替换）"
        rm -rf venv
    fi
    info "创建虚拟环境 venv/（$PY）"
    "$PY" -m venv venv || fail "venv 创建失败（Debian/Ubuntu 需先: apt install python3-venv）"
fi

# ---------- 依赖安装（按 requirements 哈希 + 导入检测跳过） ----------
reqs_hash() {
    { cat requirements.txt; cat backend/requirements.txt; } | sha256sum | cut -d' ' -f1
}

deps_ready() {
    local want; want="$(reqs_hash)"
    if [ "$FORCE" != "yes" ] && [ -f venv/.requirements-ready ] \
        && [ "$(cat venv/.requirements-ready)" = "$want" ]; then
        venv/bin/python -c 'import fastapi, sqlalchemy, aiosqlite, pydantic, pydantic_settings, openai, httpx, sklearn, jieba, numpy, apscheduler, uvicorn' 2>/dev/null
    else
        return 1
    fi
}

if deps_ready; then
    ok "依赖已安装且 requirements 未变化，跳过安装"
else
    if [ -f venv/.requirements-ready ]; then
        info "检测到 requirements 变化或强制重装，重新安装服务端依赖"
    else
        info "安装服务端依赖（requirements.txt，不含爬虫库）"
    fi
    # 用 python -m pip 而非 pip 入口脚本：后者 shebang 硬编码创建时路径，venv 目录被改名/移动后会失效
    venv/bin/python -m pip install -q --upgrade pip
    venv/bin/python -m pip install -q -r requirements.txt \
        || fail "依赖安装失败（若为 Python 版本过旧导致，建议安装 Python 3.11+ 后重试）"
    reqs_hash > venv/.requirements-ready
    ok "依赖安装完成"
fi

# ---------- 可选加速：faiss-cpu（选题验证向量召回） ----------
# 非必需：未安装时自动降级为 numpy 暴力余弦。安装失败不阻断后续流程。
venv/bin/python -m pip install -q faiss-cpu 2>/dev/null \
    && ok "faiss-cpu 已安装（选题验证向量召回加速）" \
    || warn "faiss-cpu 安装失败（可选依赖，将降级为 numpy 暴力余弦）"

# ---------- 2. .env ----------
if [ ! -f backend/.env ]; then
    cp backend/.env.example backend/.env
    warn "已从模板生成 backend/.env —— 云端 AI 至少配置一个 Key（ZHIPU_API_KEY 等），否则仅爬虫/浏览功能可用"
else
    ok "backend/.env 已存在，跳过生成"
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
    command_exists ollama || fail "ollama 未找到"
}

model_present() {
    # ollama list 显示名带 :latest 等 tag 后缀，归一化后比对
    ollama list 2>/dev/null | awk 'NR>1{print $1}' | sed 's/:[^:]*$//' | grep -Fqx "$MODEL_NAME"
}

ensure_model() {
    model_present && return 0
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

print_ollama_done() {
    cat <<EOF

$(printf "${GREEN}✔ 安装完成${NC}")
  - 向量模型: $MODEL_NAME（本地推理）
  - 已写入 backend/.env（custom_providers 合并，原有 provider 保留）

下一步:
  1. ./start.sh 启动服务
  2. 若库里已有其他模型的旧向量，执行全量重建（见 README_CN.md「本地向量模型」第4节）:
     curl -X POST "http://localhost:8000/api/topic-validator/embeddings/backfill"
  3. （可选，强烈建议）选题验证两阶段检索的重排：在 backend/.env 配 RERANK_API_KEY
     （硅基流动免费获取，配合本地 bge-m3 召回 + bge-reranker 重排，见 README_CN.md「两阶段检索」）
EOF
}

# ---------- 执行 ----------
# 自适应：运行时 + 守护进程 + 模型三者均已就绪时整体跳过（--force 可强制重新探测）
if command_exists ollama && api_alive && model_present && [ "$FORCE" != "yes" ]; then
    ok "Ollama 运行时与模型 $MODEL_NAME 均已就绪，跳过安装"
    update_env_for_ollama
    print_ollama_done
    exit 0
fi

command_exists ollama || install_ollama_runtime
ensure_daemon

# 运行时完整性探测：无模型时 embed 报错属预期，但报 llama-server 则必须重装
probe=$(curl -s --max-time 30 "$OLLAMA_URL/api/embed" -d '{"input":"ping"}' || true)
if echo "$probe" | grep -q "llama-server binary not found"; then
    install_ollama_runtime
    pkill -f "ollama serve" 2>/dev/null || true
    systemctl restart ollama 2>/dev/null || { nohup ollama serve >/dev/null 2>&1 & sleep 2; }
    ensure_daemon
fi

if ! model_present; then
    ensure_model || fail "模型 $MODEL_NAME 拉取/导入失败"
fi
info "验证向量化接口（首次调用需加载模型，CPU 数秒）..."
runtime_ok || fail "embedding 探测失败：ollama 运行时不完整或模型异常"
ok "向量化接口正常"

update_env_for_ollama
print_ollama_done

# ============================================================
# 单镜像 Dockerfile：前后端合并进一个容器
#   - 前端 Next.js standalone + rewrites 指向容器内 localhost:8000
#   - 后端 uvicorn 监听 8000
#   - 入口脚本同时启动前后端
# 构建：docker build -f Dockerfile --build-arg BACKEND_API_URL=http://localhost:8000 -t paper_hot:latest .
# ============================================================

# ---------- 前端构建（node 20, Debian slim 保证与运行镜像 glibc 兼容） ----------
FROM swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/node:20-slim AS fe-builder
WORKDIR /fe
# 前端 API 走同源 /api（容器内 rewrites 代理到 localhost:8000）
ARG NEXT_PUBLIC_API_URL=/api
# rewrites 构建期烘焙目标：单容器内后端就在 localhost:8000
ARG BACKEND_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
ENV BACKEND_API_URL=$BACKEND_API_URL
RUN npm config set registry https://registry.npmmirror.com
COPY frontend/package*.json ./
RUN npm ci --prefer-offline --no-audit
COPY frontend/ ./
RUN npm run build

# ---------- 后端依赖构建（python 3.11, 清华源加速） ----------
FROM swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.11-slim AS be-builder
WORKDIR /be
RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
    gcc libxml2-dev libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt .
RUN pip install --no-cache-dir --prefer-binary -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# ---------- 合并运行镜像 ----------
FROM swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/python:3.11-slim
WORKDIR /app

RUN sed -i 's/deb.debian.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
    libxml2 libxslt1.1 curl \
    && rm -rf /var/lib/apt/lists/*

# python 运行环境
COPY --from=be-builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=be-builder /usr/local/bin /usr/local/bin

# node 运行时（standalone 服务只需 node 二进制）
COPY --from=fe-builder /usr/local/bin/node /usr/local/bin/node

# 后端代码
COPY backend/app/ ./app/
COPY backend/requirements.txt ./
RUN mkdir -p /app/data

# 前端 standalone 产物
COPY --from=fe-builder /fe/.next/standalone ./frontend/
COPY --from=fe-builder /fe/.next/static ./frontend/.next/static

ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0 \
    NEXT_TELEMETRY_DISABLED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 入口：同时启动前后端
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 3000 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]

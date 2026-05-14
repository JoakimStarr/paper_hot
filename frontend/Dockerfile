# ============================================
# Stage 1: Builder - 构建 Next.js 应用
# ============================================
FROM swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/node:20-alpine AS builder

WORKDIR /app

# 声明构建参数
ARG NEXT_PUBLIC_API_URL=http://localhost:8000/api

# 设置环境变量供构建使用
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

# 配置 npm 使用国内镜像
RUN npm config set registry https://registry.npmmirror.com

# 复制依赖文件并安装
COPY frontend/package*.json ./
RUN npm ci --prefer-offline --no-audit

# 复制源码并构建
COPY frontend/ ./
RUN npm run build

# ============================================
# Stage 2: Production - 运行时镜像
# ============================================
FROM swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/node:20-alpine AS production

WORKDIR /app

# 安装 curl（用于健康检查）
RUN sed -i 's/dl-cdn.alpinelinux.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apk/repositories \
    && apk add --no-cache curl

# 创建非 root 用户
RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# 复制 standalone 输出文件
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

# 设置环境变量
ENV NODE_ENV=production \
    NEXT_TELEMETRY_DISABLED=1 \
    PORT=3000 \
    HOSTNAME="0.0.0.0"

# 切换到非 root 用户
USER nextjs

# 暴露端口
EXPOSE 3000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:3000/ || exit 1

# 启动命令
CMD ["node", "server.js"]

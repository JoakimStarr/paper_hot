#!/bin/bash

# 从 GitHub Release 下载论文数据库快照并解压到 backend/data/paperpulse.db
#
# 用法:
#   ./download-db.sh                 # 下载默认标签 data-20260827 的快照
#   ./download-db.sh <tag>           # 下载指定标签的快照
#   ./download-db.sh <tag> <sha256>  # 下载并用指定校验和验证
#
# 数据库已从 git/LFS 移出,以压缩资产(.gz)形式发布在 GitHub Release,
# 新机器克隆仓库后运行本脚本即可获取论文数据。

set -euo pipefail

REPO="JoakimStarr/paper_hot"
TAG="${1:-data-20260827}"
DEFAULT_SHA256="a3af6c0d0dbd1ec44dddb325cd5cb71e97787db1a4a63b988e6df2887ca9a457"
SHA256="${2:-$DEFAULT_SHA256}"

TARGET="backend/data/paperpulse.db"
URL="https://github.com/${REPO}/releases/download/${TAG}/paperpulse_release.db.gz"
TMP_GZ="$(mktemp /tmp/paperpulse_XXXXXX.db.gz)"

trap 'rm -f "$TMP_GZ"' EXIT

echo "[INFO] 下载数据库快照: ${URL}"
curl -fL -C - -o "$TMP_GZ" "$URL" || { echo "[FAIL] 下载失败(检查网络或标签 $TAG 是否存在)" >&2; exit 1; }

if [ -n "$SHA256" ]; then
    echo "[INFO] 校验 SHA256: $SHA256"
    echo "${SHA256}  ${TMP_GZ}" | sha256sum -c - >/dev/null 2>&1 \
        || { echo "[FAIL] 校验和不匹配,请确认下载完整" >&2; exit 1; }
fi

mkdir -p backend/data
echo "[INFO] 解压并写入 ${TARGET}"
gzip -dc "$TMP_GZ" > "$TARGET"

echo "[OK] 数据库就绪: ${TARGET}"
echo "     大小: $(du -h "$TARGET" | cut -f1)"
echo "     下一步: ./start.sh"

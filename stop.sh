#!/bin/bash
# 兼容入口：停止服务统一委托 start.sh stop
# （历史独立实现曾硬编码 8000 端口并 pkill 全机 next dev，存在误杀风险，已废弃）
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/start.sh" stop "$@"

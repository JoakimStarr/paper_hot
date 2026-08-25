#!/bin/bash
# 兼容入口：开发模式统一委托 start.sh dev
# （历史独立实现曾硬编码错误项目路径，已废弃；保留本文件仅为兼容旧命令习惯）
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/start.sh" dev "$@"

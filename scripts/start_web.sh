#!/usr/bin/env bash
# 从任意目录启动本机会话客户端，不改变网络或服务器管理配置。
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$project_dir"
if [[ ! -x .venv/bin/python ]]; then
  echo '未找到项目 .venv，请先按 README 安装依赖。' >&2
  exit 1
fi
echo 'Harness 会话客户端：默认 http://127.0.0.1:8765（自定义端口见服务日志）'
echo '关闭此终端或按 Ctrl+C 可停止服务。'
exec .venv/bin/python -m safety_harness.web "$@"

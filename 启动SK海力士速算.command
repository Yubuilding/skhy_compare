#!/bin/zsh

cd "$(dirname "$0")" || exit 1

if ! command -v python3 >/dev/null 2>&1; then
  echo "未找到 Python 3，暂时无法启动。"
  echo "请先从 https://www.python.org/downloads/macos/ 安装 Python 3，然后重新双击本文件。"
  echo ""
  read "?按回车键关闭窗口……"
  exit 1
fi

exec /usr/bin/env python3 app.py

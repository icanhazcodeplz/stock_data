#!/usr/bin/env bash
# PostToolUse hook (matcher: Write|Edit) — auto-fix and format the edited file
# with ruff, in place. Only touches .py files; best-effort, never blocks.
set -euo pipefail

f=$(jq -r '.tool_input.file_path // empty')

# Only Python files.
case "$f" in
  *.py) ;;
  *) exit 0 ;;
esac
[ -f "$f" ] || exit 0

uv run ruff check --fix "$f" >/dev/null 2>&1 || true
uv run ruff format "$f" >/dev/null 2>&1 || true
exit 0

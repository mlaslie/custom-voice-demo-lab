#!/bin/sh
# Plugin runtime entry point for Google Antigravity (primary) and Claude Code:
#   launch.sh mcp     -> MCP stdio server
#   launch.sh ensure  -> ensure local backend daemon is running and print its base URL
#   launch.sh serve   -> run local FastAPI backend in foreground
# The venv lives outside the plugin folder (Antigravity installs plugins read-only).
# stdout is reserved for MCP / caller output, so setup diagnostics go to stderr.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOME_DIR="${DEMOLAB_HOME:-$HOME/.demolab}"
export UV_PROJECT_ENVIRONMENT="${DEMOLAB_VENV:-$HOME_DIR/venv}"
if ! command -v uv >/dev/null 2>&1; then
  for p in "$HOME/.local/bin/uv" /opt/homebrew/bin/uv /usr/local/bin/uv; do [ -x "$p" ] && PATH="$(dirname "$p"):$PATH" && break; done
fi
command -v uv >/dev/null 2>&1 || { echo "Voice Demo Lab plugin needs uv (https://docs.astral.sh/uv/)." >&2; exit 1; }
mkdir -p "$HOME_DIR"
uv sync --project "$ROOT" --frozen --no-dev --quiet >&2
exec uv run --project "$ROOT" --frozen --no-sync python -m demolab "$@"

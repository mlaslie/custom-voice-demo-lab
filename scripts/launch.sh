#!/bin/sh
# Plugin entry point for Claude Code and Antigravity: `launch.sh mcp` (MCP over stdio) or `launch.sh open`.
# The venv lives outside the plugin folder (Antigravity installs plugins read-only). stdout is reserved
# for the MCP protocol, so setup output goes to stderr.
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOME_DIR="${DEMOLAB_HOME:-$HOME/.demolab}"
export UV_PROJECT_ENVIRONMENT="${DEMOLAB_VENV:-$HOME_DIR/venv}"
if ! command -v uv >/dev/null 2>&1; then
  for p in "$HOME/.local/bin/uv" /opt/homebrew/bin/uv /usr/local/bin/uv; do [ -x "$p" ] && PATH="$(dirname "$p"):$PATH" && break; done
fi
command -v uv >/dev/null 2>&1 || { echo "Voice Demo Lab needs uv (https://docs.astral.sh/uv/)." >&2; exit 1; }
mkdir -p "$HOME_DIR"
uv sync --project "$ROOT" --frozen --no-dev --quiet >&2
if [ ! -f "$HOME_DIR/.chromium-ok" ]; then
  uv run --project "$ROOT" --frozen --no-sync python -m playwright install chromium >&2 && touch "$HOME_DIR/.chromium-ok"
fi
exec uv run --project "$ROOT" --frozen --no-sync python -m demolab "$@"

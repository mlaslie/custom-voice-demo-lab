"""Internal plugin runtime entrypoints: `python -m demolab mcp | serve | ensure`.

Voice Demo Lab runs strictly as an Antigravity (and Claude Code) plugin — never as a standalone user CLI.
"""
from __future__ import annotations

import argparse


def main() -> None:
    ap = argparse.ArgumentParser(prog="demolab", description="Voice Demo Lab plugin runtime")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="run the local plugin backend + studio assets on 127.0.0.1")
    s.add_argument("--port", type=int)
    sub.add_parser("mcp", help="run the MCP server over stdio")
    sub.add_parser("ensure", help="ensure the local plugin backend is running and print its loopback URL")
    a = ap.parse_args()

    if a.cmd == "serve":
        import uvicorn
        from . import config
        uvicorn.run("demolab.api:app", host="127.0.0.1", port=a.port or config.PORT, log_level="warning")
    elif a.cmd == "mcp":
        from .mcp_server import main as run
        run()
    elif a.cmd == "ensure":
        from .client import ensure_server
        print(ensure_server(), flush=True)


if __name__ == "__main__":
    main()

"""demolab serve | mcp | open | setup"""
from __future__ import annotations

import argparse
import subprocess
import sys
import webbrowser


def main() -> None:
    ap = argparse.ArgumentParser(prog="demolab")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="run the web app + API on 127.0.0.1")
    s.add_argument("--port", type=int)
    sub.add_parser("mcp", help="run the MCP server on stdio")
    sub.add_parser("open", help="start the service if needed and open the web app")
    sub.add_parser("setup", help="install the Chromium build Playwright needs")
    a = ap.parse_args()

    if a.cmd == "serve":
        import uvicorn
        from . import config
        uvicorn.run("demolab.api:app", host="127.0.0.1", port=a.port or config.PORT, log_level="info")
    elif a.cmd == "mcp":
        from .mcp_server import main as run
        run()
    elif a.cmd == "open":
        from .client import ensure_server
        url = ensure_server()
        webbrowser.open(url)
        print(url)
    elif a.cmd == "setup":
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)


if __name__ == "__main__":
    main()

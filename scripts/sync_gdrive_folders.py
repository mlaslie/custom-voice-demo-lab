#!/usr/bin/env python3
"""Sync multi-level Google Drive folder hierarchy (`parent_id`) into Voice Demo Studio via `gdrive`."""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import pathlib
import subprocess
import urllib.request


def list_subfolders(parent_id: str) -> list[dict]:
    res = subprocess.run(
        ["gdrive", "readonly", "search", "--parent-id", parent_id, "--type", "folder", "--max", "200", "--json"],
        capture_output=True,
        text=True,
        timeout=20,
    )
    if res.returncode != 0 or not res.stdout.strip():
        return []
    raw = json.loads(res.stdout)
    items = raw.get("files") if isinstance(raw, dict) else raw
    out = []
    for f in items or []:
        if f.get("id") and f.get("name"):
            out.append(
                {
                    "id": f["id"],
                    "name": f["name"],
                    "parent_id": "root" if parent_id == "root" else parent_id,
                    "shared": False,
                }
            )
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", default="", help="Signed-in Google Drive account email")
    ap.add_argument("--depth", type=int, default=2, help="Folder recursion depth (default: 2)")
    args = ap.parse_args()

    all_folders: list[dict] = []
    frontier = ["root"]
    for _ in range(max(1, args.depth)):
        if not frontier:
            break
        next_frontier: list[str] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            futs = [ex.submit(list_subfolders, pid) for pid in frontier]
            for fut in concurrent.futures.as_completed(futs):
                children = fut.result()
                all_folders.extend(children)
                next_frontier.extend(c["id"] for c in children)
        frontier = next_frontier

    home = pathlib.Path.home() / ".demolab"
    port = (home / "port").read_text().strip()
    payload = json.dumps(
        {
            "connected": True,
            "account_email": args.email,
            "folders": all_folders,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/gdrive/state",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        out = json.loads(resp.read().decode("utf-8"))
    print(f"Synced {len(out.get('folders', []))} folders for {out.get('account_email') or 'Google Drive'}.")


if __name__ == "__main__":
    main()

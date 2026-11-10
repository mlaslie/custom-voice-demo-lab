# Developing Voice Demo Lab

## Layout

| Path | What |
|---|---|
| `demolab/` | Python service: FastAPI app (`api.py`), MCP server (`mcp_server.py`), settings, keys and voice profiles (`config.py`), Gemini TTS and voice listing (`gemini.py`), decks (`sources.py`), the script guide and checks (`script.py`), narration, pacing, verification and render (`pipeline.py`), browser automation and recorder (`browser.py`), title cards (`cards.py`), composer (`compose.py`) |
| `demolab/static/` | Built web app (committed so plugin installs need no Node) |
| `web/` | React + Vite + Tailwind source: `npm install && npm run build` writes to `demolab/static/` |
| `skills/voice-demo/` | Agent skill shared by both hosts |
| `.claude-plugin/`, `.mcp.json` | Claude plugin and marketplace |
| `.antigravity-plugin/`, `mcp_config.json` | Antigravity plugin |
| `scripts/launch.sh` | Plugin entry point (`mcp`, `serve`, `open`, `setup`) |
| `tests/` | pytest suite |

## Running it

```bash
uv sync
uv run demolab serve                 # API + built UI on :8765
cd web && npm install && npm run dev # UI with hot reload on :5173 (proxies /api)
uv run --group dev pytest
```

`./scripts/launch.sh open` starts the service the way the plugin does (venv in `~/.demolab/venv`) and opens
the studio.

`DEMOLAB_FAKE_GEMINI=1` runs everything without calling Gemini: keys are accepted without checking, a few
fake voices are listed, and narration is silent. Handy for UI work and tests. The test suite never touches
the real OS keychain (see `tests/conftest.py`).

## Runtime details

- **Port:** the service listens on 127.0.0.1:8765 (`$DEMOLAB_PORT`). If another program holds that port, it
  picks a free one and records it in `~/.demolab/port`, so every MCP server and `launch.sh open` finds it.
  It rejects requests with a non-local `Host` header, and writes whose `Origin` is another site.
- **Data:** `~/.demolab/` (override with `$DEMOLAB_HOME`): `settings.json` (keys' names and last four
  characters, voice profiles, models, render folder) and `projects/<id>/` (script, slide images, narration
  cache, dry-run screenshots).
- **Secrets:** API keys live in the OS keychain under the `demolab` service (a 0600 `secrets.json` is the
  fallback when no keychain backend exists). `$GEMINI_API_KEY` overrides saved keys.
- **Renders:** go to the render folder from Settings. If it is on an external drive that is not mounted,
  renders stop with an error instead of falling back to the internal disk.
- **Slide images from .pptx:** LibreOffice if installed, else Keynote on macOS (AppleScript export).

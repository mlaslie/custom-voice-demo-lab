# Developing Voice Demo Lab

## Plugin Layout

| Path | Purpose |
|---|---|
| `plugin.json`, `.antigravity-plugin/plugin.json`, `mcp_config.json` | Google Antigravity plugin manifests & MCP server config |
| `sidecars/studio/` | Antigravity Auxiliary Pane UI Sidecar (`sidecar.json` + `main.mjs` bridging `sidecar_sdk`, static Studio assets, and live `GetAllPlugins` Drive plugin detection to the local Python service) |
| `agents/demo-researcher.md` | Specialist research subagent for grounding scripts in official docs, blogs, release notes, and videos |
| `skills/voice-demo/SKILL.md` | End-to-end orchestration workflow for slide, website, and hybrid demos, in-AGY browser onboarding, and Google Drive export |
| `rules/AGENTS.md` | Always-on plugin safety & routing rules |
| `.claude-plugin/`, `.mcp.json` | Secondary Claude Code plugin manifests |
| `scripts/launch.sh` | Internal plugin runtime launcher (`mcp`, `ensure`, `serve`; manages `~/.demolab/venv`) |
| `scripts/sync_gdrive_folders.py` | Syncs multi-level Google Drive folder hierarchy (`parent_id`) via Antigravity's `gdrive` CLI into Studio's graphical folder picker |
| `demolab/` | Python backend: FastAPI (`api.py`), MCP server (`mcp_server.py`), data models (`models.py`), settings & keychain (`config.py`), native Save-As dialog & Google Drive folder cache (`gdrive_store.py`), Gemini TTS (`gemini.py`), Google Slides/PDF/PPTX ingestion (`sources.py`), AGY browser onboarding & frame manager (`agy_browser.py`), pure-Pillow 2× supersampled cards (`cards.py`), script guide & validator (`script.py`), 1080p compositor (`compose.py`), and render pipeline (`pipeline.py`) |
| `web/` -> `demolab/static/` | React + TypeScript + Tailwind Studio UI, including `DriveFolderModal.tsx` (`cd web && npm install && npm run build`) |
| `tests/` | Automated `pytest` suite (`uv run pytest`) |

## Local Development & Testing

```bash
uv sync
uv run pytest -v
cd web && npm install && npm run build
```

- Set `DEMOLAB_FAKE_GEMINI=1` for offline tests/development (synthesizes silent WAVs and mock voice lists without network calls).
- `tests/conftest.py` disables OS keychain access automatically during `pytest` so your real `~/.demolab` keys and profiles are never touched.

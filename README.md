# Voice Demo Lab

Narrated demo videos of web apps and slide decks in **your own custom Gemini TTS voice**.

1. **Sources**: point it at a live web app, a source folder, a PowerPoint/PDF, a Google Slides deck, or
   paste notes or an existing script. When you ask from a coding session ("make a demo of what we just
   built"), the agent adds **session context**: a brief of the goal, what was built and why, what to show
   and what to avoid, plus the key files and screenshots. The script is built around it.
2. **Script**: Gemini drafts the narration (title cards, slide narration, web steps). You edit it, hear
   any line in your voice, ask AI to revise a segment, and approve.
3. **Rehearse** (web apps): Gemini explores the app and plans the clicks for each step against the real
   page; you edit them; a dry run checks every action.
4. **Render**: narration (cached), title cards, slides and a real-time screencast of the web steps are
   composed into a 1080p MP4. Long waits are fast-forwarded behind a banner, and silences are tightened
   to a presenter's pace.

It runs locally as a web app plus an MCP server, packaged as a plugin for **Claude Code** and
**Google Antigravity**. Both talk to the same local service, so you can drive it from an agent and
review in the browser.

## Requirements

- macOS or Linux with [uv](https://docs.astral.sh/uv/) and `ffmpeg` (`brew install uv ffmpeg`)
- A Gemini API key **from the AI Studio project that owns your custom voice**. Custom voices are scoped
  to the project that created them, so a key from another project gets a 404.
- Optional: LibreOffice (`brew install --cask libreoffice`) for slide *images* from .pptx files.
  Without it, PowerPoint decks give text and speaker notes only (or upload the deck's PDF export).
- Optional: a Google OAuth client for Google Slides, set up as described in [docs/google-oauth.md](docs/google-oauth.md).

The first launch installs the Python environment (`~/.demolab/venv`) and Playwright's Chromium.

## Install

### Claude Code

```
/plugin marketplace add mlaslie/custom-voice-demo-lab
/plugin install custom-voice-demo-lab@voice-demo-lab
```

The repo is private, so your `gh`/git credentials must have access. You can also install from a local
clone: `/plugin marketplace add ~/path/to/custom-voice-demo-lab`.

### Google Antigravity

```
agy plugin install https://github.com/mlaslie/custom-voice-demo-lab
```

Or install from a local clone with `agy plugin install ~/path/to/custom-voice-demo-lab`, or `/plugin install <path>` inside the CLI.

### Standalone

```
./scripts/launch.sh open      # starts http://127.0.0.1:8765 and opens it
```

## First run

Open the web app (ask the agent to "open Voice Demo Lab", or run `scripts/launch.sh open`) and go to
**Settings**:

- **Custom voice id**: e.g. `voice_…` from aistudio.google.com
- **Gemini API key**: stored in the macOS Keychain (`demolab` service). It is never shown again, never
  sent to the browser, and never accepted through MCP tools. `$GEMINI_API_KEY` overrides it.
- **Render folder**: point it at an external drive for long demos. If that drive is not mounted, renders
  stop with an error instead of falling back to the internal disk.

## Using it from an agent

The plugin adds the `voice-demo` skill and the `demolab` MCP server. Try:

- "Make a narrated demo of the app on localhost:8090 showing how to create and test a policy"
- "Turn ~/Desktop/pitch.pptx into a narrated video in my voice"
- "Open the Voice Demo Lab on the retail project"

The agent drafts and revises, then hands you the studio link to review. It approves the script only
when you say so.

## Layout

| Path | What |
|---|---|
| `demolab/` | Python service: FastAPI app (`api.py`), MCP server (`mcp_server.py`), Gemini (`gemini.py`), sources, script writer, browser automation and recorder (`browser.py`), composer (`compose.py`) |
| `demolab/static/` | Built web app (committed so plugin installs need no Node) |
| `web/` | React + Vite + Tailwind source: `npm install && npm run build` writes to `demolab/static/` |
| `skills/voice-demo/` | Agent skill shared by both hosts |
| `.claude-plugin/`, `.mcp.json` | Claude Code plugin + marketplace |
| `.antigravity-plugin/`, `mcp_config.json` | Antigravity plugin |
| `scripts/launch.sh` | Plugin entry point (`mcp`, `serve`, `open`, `setup`) |

Data lives in `~/.demolab/` (override with `$DEMOLAB_HOME`). Each project's sources, slides, narration
cache and dry-run screenshots live in `projects/<id>/`.

## Development

```
uv sync
uv run demolab serve                 # API + built UI on :8765
cd web && npm install && npm run dev # UI with hot reload on :5173 (proxies /api)
uv run --group dev pytest
```

`DEMOLAB_FAKE_GEMINI=1` runs the whole pipeline without calling Gemini (silent narration, template
scripts, trivial action plans), which is handy for UI work and tests.

# Voice Demo Lab

Narrated demo videos of what your coding session worked on, in **your own custom Gemini TTS voice** or
any standard Gemini voice, made from inside **Claude Code** or **Google Antigravity**.

Analyze some code, a running app or a slide deck with your agent, then ask it for a demo video:

1. **The session writes the script.** The agent that did the analysis writes the narration itself,
   following the plugin's guide (format, house style, writing for the ear). The plugin checks it. Decks
   the session used (.pptx or .pdf files; the agent exports Google Slides decks with its own Google
   tools) become the video's slides; a running app is recorded live, with click steps the agent
   writes from the code and checks against the real page.
2. **You review it beside the chat.** The studio opens in the session's side panel: edit any line, hear it
   in the voice, and approve. Or ask the agent for changes in the chat.
3. **Gemini voices it and the video is rendered**, only after you approve. Narration (cached), title
   cards, slides and a real-time screencast of the web steps are composed into a 1080p MP4. Long waits are
   fast-forwarded behind a banner, and silences are tightened to a presenter's pace.

Gemini is used only for text-to-speech; it never writes the script.

It runs locally as a small web app (the studio) plus an MCP server, packaged as a plugin for both hosts.

## Requirements

- macOS or Linux with [uv](https://docs.astral.sh/uv/) and `ffmpeg` (`brew install uv ffmpeg`)
- A Gemini API key **from the AI Studio project that owns your custom voice**. Custom voices are scoped
  to the project that created them, so a key from another project gets a 404.
- For slide *images* from .pptx files: LibreOffice (`brew install --cask libreoffice`) or, on macOS, Keynote
  (it asks once for permission to be controlled). Without either, PowerPoint decks give text and speaker
  notes only (or pass the deck's PDF export).

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

The first time the plugin is used (or whenever no voice is set up), the agent opens the **setup page**
beside the chat, in the host's built-in browser, or in your system browser:

1. **Add a Gemini API key.** It is sent only to the local service, checked with Gemini, and stored in your
   system keychain (`demolab` service). It is never shown again, never returned by the API, and never
   accepted through MCP tools or the chat. `$GEMINI_API_KEY` overrides saved keys when set.
2. **Choose a voice.** The page lists the custom voices in that key's AI Studio project, plus the standard
   Gemini voices: 30 multilingual ones and about 2,000 more in 40 languages, by role (podcaster,
   storyteller, training voiceover, …). Play a sample of any of them.
3. **Name it and set the delivery style.** This saves a **voice profile** and makes it active for this and
   future sessions.

You can save several keys and several voice profiles, switch the active one from the sidebar or Settings,
or give a project its own voice (**Brief & voice**). Agents switch with `use_voice_profile`. In Settings
you can also set the render folder: if it is on an external drive that is not mounted, renders stop with an
error instead of falling back to the internal disk.

## Using it from an agent

The plugin adds the `voice-demo` skill and the `demolab` MCP server. In a session where you have been
working on something, try:

- "Create a demo video of the policy editor we just reviewed, running on localhost:8090"
- "Make a narrated video of the deck we went through, in the formal voice"
- "Switch the narrator to Kore for this demo"

The agent writes the script, opens it beside the chat, and renders only after you approve it.

## Layout

| Path | What |
|---|---|
| `demolab/` | Python service: FastAPI app (`api.py`), MCP server (`mcp_server.py`), Gemini TTS (`gemini.py`), decks (`sources.py`), the script guide and checks (`script.py`), browser automation and recorder (`browser.py`), composer (`compose.py`) |
| `demolab/static/` | Built web app (committed so plugin installs need no Node) |
| `web/` | React + Vite + Tailwind source: `npm install && npm run build` writes to `demolab/static/` |
| `skills/voice-demo/` | Agent skill shared by both hosts |
| `.claude-plugin/`, `.mcp.json` | Claude Code plugin + marketplace |
| `.antigravity-plugin/`, `mcp_config.json` | Antigravity plugin |
| `scripts/launch.sh` | Plugin entry point (`mcp`, `serve`, `open`, `setup`) |

The service uses port 8765 (`$DEMOLAB_PORT`); if another program holds it, it picks a free port and records
it in `~/.demolab/port`. Data lives in `~/.demolab/` (override with `$DEMOLAB_HOME`). Each project's slides, narration
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

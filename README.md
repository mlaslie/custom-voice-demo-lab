# Voice Demo Lab

Automate research-grounded, 1080p narrated demo and overview videos from **slides** or **live websites** — orchestrated end-to-end as a plugin inside **Google Antigravity** (primary) and compatible with **Claude Code**, voiced in **your custom Gemini TTS voice** or any standard Gemini voice.

> **Plugin-Only Architecture (`v0.4.0`)**: Voice Demo Lab runs strictly as an AI coding-environment plugin (MCP server + Antigravity Sidecar Studio panel + research subagent + skill) — zero standalone CLI mode and zero external Playwright browser windows.

## Supported Demo Scenarios

1. **In-Antigravity Created Slides + Session Context + Instructions**
   Build a Google Slides deck (or PDF/PPTX) during your Antigravity session, then ask Antigravity to turn it into a narrated demo video. It combines your slides, speaker notes, and session context with verified technical research.
2. **User-Provided Slides + Context + Directions**
   Provide an existing Google Slides URL/ID, `.pdf`, or `.pptx` deck along with your context and directions (audience, tone, target length, focus areas).
3. **Live Website Walkthrough in Antigravity's Built-In Browser**
   Point Antigravity at any live web app or cloud console (e.g. `https://console.cloud.google.com` or `localhost:3000`). Antigravity runs an **interactive login onboarding check** inside the Antigravity Browser pane first (pausing so you can sign in if needed), explores the real UI, captures crisp 1080p `before` / `during` / `result` step frames with spotlight callouts and smooth zooms, and renders the narrated walkthrough.
4. **Hybrid (Slides + Live Website)**
   Combine Google Cloud styled title cards, architecture slides, and live browser walkthrough steps in a single cohesive MP4.

## Key Capabilities

- **Reality-Grounded Script Builder (`demo-researcher` + `save_research`)**: Researches slide claims, website workflows, and session context against authoritative technical documentation, recent launch blogs, release notes, and videos before writing a word of narration—showing exact source citations beside each segment in Voice Demo Studio.
- **Native Antigravity Sidecar UI (`Voice Demo Studio`)**: Opens right in Antigravity's auxiliary side pane (`sidecar://custom-voice-demo-lab/studio/`). Edit narration inline, preview any segment in your voice, inspect grounded citations and captured browser frames, click **Approve & Render in AGY**, and watch rendered MP4s.
- **100% In-Antigravity Browser Onboarding & Capture**: Uses Antigravity's built-in `browser` subagent for sign-in checks, interactive login onboarding, UI exploration, and 1080p frame capture—with spotlight callouts (`HighlightBox`), smooth zoom-ins (`zoom_to`), and fast-forward banners (`ff_what`) for long cloud deployments.
- **Custom & Standard Gemini Voices + OS Keychain Security**: Pair Gemini API keys (stored exclusively in your macOS/OS keychain—never passed through chat) with custom AI Studio voices or 2,100+ standard voices across 39 locales, with per-profile verification and 0.7×–1.4× pitch-preserving pacing.

## Requirements

- macOS or Linux with [uv](https://docs.astral.sh/uv/) and `ffmpeg`:
  ```bash
  brew install uv ffmpeg
  ```
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey) (for custom voices, use a key from the AI Studio project that created the voice).
- Optional for `.pptx` decks: LibreOffice or macOS Keynote (Google Slides and `.pdf` decks render natively with zero extra dependencies).

## Install

### Google Antigravity (Recommended)

```bash
agy plugin install https://github.com/mlaslie/custom-voice-demo-lab
```

Start a new Antigravity conversation after installing (or updating).

### Claude Code

```bash
claude plugin marketplace add mlaslie/custom-voice-demo-lab
claude plugin install custom-voice-demo-lab@voice-demo-lab
```

## First-Time Voice Setup

On first use, Antigravity surfaces the **Voice Demo Studio** pill (`[Voice Demo Studio](sidecar://custom-voice-demo-lab/studio/)`) in chat:

1. **Add your Gemini API key** on the Studio Setup page — saved straight to your OS keychain and never exposed to chat or MCP logs.
2. **Pick your custom or standard voice** and preview a sample clip.
3. **Save & verify** — Voice Demo Lab synthesizes a short test phrase and marks the profile **Verified**.

## Example Prompts in Antigravity

- *"Create a demo video of the Gemini for Healthcare Google Slides presentation we just built, keeping it around 3 minutes."*
- *"Use Voice Demo Lab to turn `https://docs.google.com/presentation/d/...` into an executive overview video, grounded in the latest Google Cloud docs."*
- *"Build a walkthrough demo video of enabling and configuring a FHIR store on `https://console.cloud.google.com/healthcare` using the Antigravity browser."*

## Privacy & Security

- Runs 100% locally on your machine (`127.0.0.1` with DNS-rebinding, `Origin`, and Antigravity `X-Sidecar-Token` guards).
- Gemini API keys live in your OS keychain (`keyring` service `demolab`); callers only ever see the key label and last 4 characters.
- Website authentication happens exclusively inside your own Antigravity Browser pane—credentials are never read or handled by the plugin.

## Development

See [docs/development.md](docs/development.md) for architecture layout, sidecar details, and running the `pytest` suite.

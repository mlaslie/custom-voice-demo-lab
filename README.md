# Voice Demo Lab

Automate research-grounded, 1080p narrated demo and overview videos from **slides** or **live websites** — orchestrated end-to-end as a plugin inside **Google Antigravity** (primary) and compatible with **Claude Code**, voiced in **your custom Gemini TTS voice** or any standard Gemini voice.

> **Plugin-Only Architecture (`v0.5.0`)**: Voice Demo Lab runs strictly as an AI coding-environment plugin (MCP server + Antigravity Sidecar Studio panel + research subagent + skill) — with zero standalone CLI commands and zero external Playwright browser windows.

---

## Supported Demo Scenarios

1. **Slides Created in Antigravity + Session Context + Instructions**
   Build a Google Slides deck (or PDF/PPTX) during your Antigravity session, then ask Antigravity to turn it into a narrated video. It combines your slides, speaker notes, session context, and verified technical research into a cohesive script.
2. **User-Provided Slides + Context + Directions**
   Point Antigravity at an existing Google Slides URL/ID, `.pdf`, or `.pptx` deck along with your audience, tone, target runtime, and focus areas.
3. **Live Website Walkthroughs in Antigravity's Built-In Browser**
   Give Antigravity any live web app or cloud console URL (for example `https://console.cloud.google.com` or `http://localhost:3000`). Antigravity runs an **interactive login onboarding check** inside your Antigravity Browser pane first (pausing so you can sign in if needed), explores the live UI, captures crisp 1080p `before` / `during` / `result` frames with spotlight callouts and smooth zooms, and renders the narrated video.
4. **Hybrid (Slides + Live Website)**
   Blend 2× supersampled title cards, architecture slides, and live browser walkthrough steps into a single 1080p MP4.

---

## Voice Demo Studio (Side Panel Walkthrough)

Voice Demo Studio opens directly in Google Antigravity's auxiliary side pane (`[Voice Demo Studio](sidecar://custom-voice-demo-lab/studio/)`) right beside your chat.

### 1. Reality-Grounded Script Editor & Voice Preview
Before drafting narration, `demo-researcher` verifies slide claims, product capabilities, recent launch blogs, release notes, and documentation — attaching verified citations right above and beside your script segments. Edit any line inline, adjust pacing (`0.70×`–`1.40×` with pitch preserved), preview individual segments in your voice, and approve when ready.

![Voice Demo Studio — Grounded Research and Script Tab](docs/screenshots/studio-script-tab.png)

### 2. 100% In-Antigravity Browser Onboarding & Frame Capture
Website and hybrid demos run exclusively inside Antigravity's built-in browser. Studio tracks sign-in onboarding status and previews captured `before`, `during`, and `result` 1080p frames, action choreography, spotlight highlights, and fast-forward wait banners.

![Voice Demo Studio — In-AGY Browser Onboarding and Step Frames](docs/screenshots/studio-browser-tab.png)

### 3. 1080p MP4 Rendering & Local Save-As Download
Once readiness checks pass, Voice Demo Lab synthesizes Gemini TTS audio, composes 2× supersampled title cards, slides, and browser frames, and tightens pauses to a natural presenter cadence. Clicking **Download MP4** opens a native OS **Save As** file picker so you can choose the exact destination folder and filename on your machine.

![Voice Demo Studio — Render Tab and 1080p Video Player](docs/screenshots/studio-render-tab.png)

### 4. Graphical Google Drive Export (`gdrive` Integration)
Export rendered MP4s straight to Google Drive through Antigravity's official **Google Drive (`gdrive`)** plugin:
- If `gdrive` is not yet installed, disabled, or signed out in Antigravity, **Push to Google Drive** stays greyed out with an adjacent **Install Google Drive** / **Sign in to Google Drive** button right next to it to initiate setup in one click.
- Once connected, clicking **Push to Google Drive** opens a graphical folder browser with `My Drive › …` breadcrumbs, nested subfolder drill-down, search filtering, and inline **+ New Folder** creation, then adds an **Open in Google Drive** link directly on the render card.

![Voice Demo Studio — Graphical Google Drive Folder Picker](docs/screenshots/studio-drive-folder-picker.png)

---

## Requirements

- macOS or Linux with [uv](https://docs.astral.sh/uv/) and `ffmpeg`:
  ```bash
  brew install uv ffmpeg
  ```
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey) (to use a custom voice, create the key in the same AI Studio project that owns the voice).
- Optional:
  - **Google Slides / Google Drive plugins** in Antigravity (`gslides` for native Google Slides export; `gdrive` for graphical Drive uploads).
  - **LibreOffice** or **Keynote** (macOS) if importing `.pptx` files directly (`.pdf` and exported Google Slides decks require neither).

---

## Install

### Google Antigravity (Recommended)

```bash
agy plugin install https://github.com/mlaslie/custom-voice-demo-lab
```

Start a new Antigravity conversation after installing. To upgrade later:

```bash
agy plugin uninstall custom-voice-demo-lab
agy plugin install https://github.com/mlaslie/custom-voice-demo-lab
```

### Claude Code

In a Claude Code session (terminal or Claude desktop **Code** tab):

```text
/plugin marketplace add mlaslie/custom-voice-demo-lab
/plugin install custom-voice-demo-lab@voice-demo-lab
```

Or from a terminal:

```bash
claude plugin marketplace add mlaslie/custom-voice-demo-lab
claude plugin install custom-voice-demo-lab@voice-demo-lab
```

---

## First-Time Voice Setup

On first use, Antigravity surfaces the **Voice Demo Studio** pill in chat:

1. **Add your Gemini API key** on the Studio Setup page — saved directly to your OS keychain (`keyring`) and never passed through chat or MCP tool arguments.
2. **Select a custom or standard voice** (over 2,100 voices across 39 locales) and play a sample clip.
3. **Set a label, description, and pace** — Voice Demo Lab speaks a short verification phrase and marks the profile **Verified**.

---

## Example Prompts

- *"Create a 2-minute narrated demo video from the architecture slides we just created in this session."*
- *"Turn `https://docs.google.com/presentation/d/...` into an executive overview video grounded in the latest product documentation."*
- *"Create a short walkthrough demo video for `https://console.cloud.google.com` showing how to inspect deployed enterprise AI applications using the Antigravity browser."*
- *"Combine our intro slides with a live walkthrough of `http://localhost:3000` in my custom narrator voice, paced 5% faster."*

---

## Privacy & Security

- **100% Local Execution**: Runs locally on `127.0.0.1` protected by DNS-rebinding, `Origin`, and Antigravity `X-Sidecar-Token` verification.
- **Keychain-Only API Keys**: Gemini API keys are stored exclusively in your OS keychain (`demolab` service); tools and UI responses expose only the key label and last four characters.
- **In-Browser Authentication**: Live website sessions stay inside your own Antigravity Browser pane — credentials and cookies are never read or stored by Voice Demo Lab.

---

## Development

See [docs/development.md](docs/development.md) for the plugin directory layout, sidecar architecture, and running the automated `pytest` suite.

Voice Demo Lab is an independent project. It is not made or endorsed by Google or Anthropic.

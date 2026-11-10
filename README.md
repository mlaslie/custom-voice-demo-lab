# Voice Demo Lab

Turn what you just worked on with your coding agent into a narrated demo video, in **your own custom
Gemini voice** or any standard Gemini voice.

Voice Demo Lab is a plugin for **Claude Code** and **Google Antigravity**. Review some
code, a running app or a slide deck with your agent, then ask it for a demo video. The agent writes the
script from what the session learned, you approve it in a panel beside the chat, and the plugin voices it
and renders a 1080p MP4.

## What it does

1. **Your agent writes the script.** The agent that did the work writes the narration, following the
   plugin's guide to format, house style and writing for the ear. The plugin checks it before saving.
2. **You review it beside the chat.** The studio opens in the session's side panel. Edit any line, hear it
   in your voice, and approve it, or ask the agent for changes in the chat.
3. **The video is made after you approve.** Gemini text-to-speech speaks the script, and the plugin
   composes title cards, your slides and live recordings of your app into a video. Long waits are
   fast-forwarded behind a banner, and pauses are tightened to a presenter's pace.

Along the way it handles:

- **Slides:** the decks your session used (.pptx or .pdf) become the video's slides. Google Slides decks
  are exported to a file by your agent's own Google tools.
- **Live apps:** a running web app is recorded in a real browser, with clicks the agent writes from your
  code and checks against the real page first.
- **Voices:** your custom voices from Google AI Studio, or any of about 2,100 standard voices in 39
  languages. Save several key and voice pairs, each with a label and description, and switch between
  them. Every pair is tested with a spoken phrase and marked **Verified**.
- **Pacing:** set a voice's speed with − / + controls and check it with a test clip that reports the
  words per minute. A single demo can use its own pace.

Gemini is only used to speak the script. It never writes it.

## Requirements

- macOS or Linux, with [uv](https://docs.astral.sh/uv/) and `ffmpeg`. On macOS:

  ```bash
  brew install uv ffmpeg
  ```

- A Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey). To use a custom voice,
  the key must come from the AI Studio project that created that voice.
- For slide images from PowerPoint files: LibreOffice, or Keynote on macOS. Without either, export the
  deck to PDF.

The first run installs the plugin's Python environment and a browser for recording, which takes a few
minutes.

## Install

### Claude Code

Works in the Claude Code terminal app and in the Claude desktop app's **Code** tab. In a session, run:

```
/plugin marketplace add mlaslie/custom-voice-demo-lab
/plugin install custom-voice-demo-lab@voice-demo-lab
```

Or from a terminal:

```bash
claude plugin marketplace add mlaslie/custom-voice-demo-lab
```

```bash
claude plugin install custom-voice-demo-lab@voice-demo-lab
```

Start a new session afterwards. To update later, run `claude plugin update custom-voice-demo-lab@voice-demo-lab`.

### Google Antigravity

From a terminal:

```bash
agy plugin install https://github.com/mlaslie/custom-voice-demo-lab
```

Start a new session afterwards. To update, uninstall it with `agy plugin uninstall custom-voice-demo-lab`
and install it again.

## First use

The first time you ask for a demo, the agent opens the **setup page** beside the chat:

1. **Add your Gemini API key.** It goes straight from that page to your computer's keychain. It is never
   shown again and never passes through the chat or the AI agent.
2. **Choose a voice:** one of your custom voices, or a standard voice. Play a sample of any of them.
3. **Give it a label, a description and a pace.** The voice is tested with a short spoken phrase and
   saved for future sessions.

To add more voices or keys later, open **Settings** in the studio.

## Making a demo

In a session where you've been working on something, ask for a video. For example:

- "Create a demo video of the policy editor we just reviewed. It's running on localhost:8090."
- "Make a narrated video of the deck we went through, in the formal voice."
- "Make it about 10% slower."

The agent writes the script, opens it beside the chat for you to review, and renders the video only after
you approve it. Videos are saved to the render folder set in **Settings**, and play on the studio's
**Render** tab.

## Privacy

- Everything runs on your computer. The only outside service is the Gemini API, called with your own key
  to list voices and to speak the script.
- Keys stay in your system keychain. The studio shows only a key's name and its last four characters.
- Scripts, slides and videos stay on your computer.

## More

- [Developing Voice Demo Lab](docs/development.md): the code layout, running it locally, and tests.

Voice Demo Lab is an independent project. It is not made or endorsed by Google or Anthropic.

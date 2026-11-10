---
name: voice-demo
description: >-
  Make a narrated demo video of a web app or a slide deck in the user's custom Gemini TTS voice, using the
  Voice Demo Lab MCP tools. Use when the user asks for a demo video, a narrated walkthrough, a voice-over
  for slides or an app, to turn a deck/notes/code into a narrated video, or to open or configure Voice
  Demo Lab (voice id, API key, Google Slides). Also use it to turn the current working session (what was
  just built, changed or discussed) into a narrated demo.
---

# Voice Demo Lab

Voice Demo Lab is a local web app plus an MCP server (`demolab`). Its tools and the web app share the same
projects, so you can work through the tools while the user reviews in the browser.

## Flow

1. **Check setup**: `get_settings`. If `voice_id` is empty or `gemini_key_set` is false, call
   `open_studio` and ask the user to fill in Settings. **Never ask for, accept, echo or store the API key
   yourself.** The key must come from the AI Studio project that created the custom voice (a key from another
   project makes the voice return 404).
2. **Create the project**: `create_project(name, base_url, goal, instructions)`. `base_url` is the web
   app to demo (leave it empty for slides-only). Put the user's wishes for tone, length and emphasis in
   `instructions`.
3. **Add session context first** when the demo is about work done or discussed in this conversation
   ("make a demo of this", "record what we just built"). Call `add_session_context` with what you know:
   the goal, what was built or changed, decisions and why, what to show and in what order, and caveats
   (unfinished or broken parts that must not be shown or claimed). Pass the files and folders that matter
   most: specs, docs, key source files, screenshots you took, decks. Pass `workspace` so relative paths
   resolve. The script writer treats this as the main story, so make it accurate and specific, and
   never attach secrets (`.env`, keys, tokens). Skip this step only when the request has nothing to do
   with the session.
4. **Add other sources** with `add_source`:
   - `url`: the live app
   - `repo`: a local code folder
   - `file`: a local .pptx/.pdf/.md/.txt
   - `gslides`: needs Google connected in Settings
   - `text`: notes or an existing script

   Slides from decks are numbered project-wide from 0.
5. **Script**: `draft_script` has Gemini write it. If the user wants you to write it, or the draft needs
   heavy rework, use `set_segments`, `update_segment` or `revise_segment`. The segment types are:
   - `card`: a title card (title, kicker, sub, bullets)
   - `slide`: shows `slide` N while narrating
   - `step`: a web step, where `narration` plays, the actions run during or after it, then `after_narration`
     says how the result shows the step worked
6. **Review**: summarise the script for the user (segment titles and narration) and give them the
   `studio_url` (or call `open_studio(project_id)`) so they can edit it and listen to previews.
   **Only call `approve_script` when the user explicitly approves.**
7. **Web steps**: if the app needs a login, call `capture_login`; the user signs in themselves in the
   window that opens. Then run `plan_actions` (Gemini explores the app and plans clicks for each step)
   and `dry_run`. Fix failures with `update_segment` (actions use Playwright selectors such as
   `role=button[name="Save"]`, `text="Exact text"` or CSS), or with `plan_actions` for those segment ids,
   until the dry run passes.
8. **Render**: `render(project_id)` starts a background job and returns at once. Recording runs in real
   time, so it can take a while; poll `get_job` now and then and report progress. The result is an MP4
   path in the output folder from Settings.

## Narration style (the user's approved defaults)

- An intro card plus a spoken introduction of what will be shown, a card per section or scenario, and a
  narrated recap card with bullets. No closing tagline.
- For each step: explain in plain terms what it does, do it, then say how the result matches the goal.
- The audience is new to the product: full coverage, but high level.
- Long waits (cloud operations, tests) get `wait_for` with `ff: true` and a short `what`, so the video
  fast-forwards them behind a banner.

## Notes

- Text for the voice should be written for the ear: short sentences, no markdown, no URLs read aloud.
- `preview_voice(text)` returns a WAV path, which is useful for checking pronunciation of product names.
- Large renders: suggest an output folder on an external drive in Settings if the user has one.

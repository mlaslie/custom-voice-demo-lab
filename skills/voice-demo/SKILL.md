---
name: voice-demo
description: >-
  Turn what this coding session analyzed (code, a running app, slides, notes) into a narrated demo video in
  the user's custom or a standard Gemini TTS voice, using the Voice Demo Lab MCP tools. You write the script
  from the session; the plugin checks it, the user approves it in a side panel, then it is voiced and
  rendered. Use when the user asks for a demo video, a narrated walkthrough or a voice-over of what the
  session worked on, or to set up or switch narrator voices (API keys, custom and standard voices).
---

# Voice Demo Lab

The session is the context. You have analyzed code, slides or an app with the user; when they ask for a
demo video, **you write the narration script** from that knowledge, following the plugin's guide. The
plugin checks it, shows it in the studio beside the chat for the user to review and approve, then Gemini
text-to-speech voices it and the video is rendered. Gemini does not write the script.

## Flow

1. **Check setup**: `get_settings`. If `setup_needed` is true (first use, or no voice yet), call
   `open_studio(page="setup", open_browser=false)` and open the returned URL in your side panel (below).
   Ask the user to add their Gemini API key and choose a voice there, and wait until they say they are
   done. **Never ask for, accept, echo or store an API key yourself**, even if the user pastes one into the
   chat: the key is only entered on the setup page, which saves it to the OS keychain.

2. **Pick the voice**: the active voice profile is used by default. If the user names a voice or a kind of
   voice ("the formal one", "use Kore"), match it with `list_voice_profiles` (each profile has a label and
   a description) and pass it to `start_demo`, or call `use_voice_profile`. To add a voice that is not
   saved, send them to `open_studio(page="settings", open_browser=false)`.

3. **Start the demo**: `start_demo(title, goal, brief, audience, instructions, base_url, decks)`.
   - `brief`: what this session established, in your own words: what was analyzed or built, how it works,
     what matters, decisions and why, what is unfinished or must not be shown. The user sees it beside the
     script.
   - `decks`: every slide deck the session used (.pptx or .pdf paths, Google Slides links). Their slides
     become the video's slide images; the result lists each slide's text and speaker notes.
   - `base_url`: the running app to record, if the video shows a live app (empty for slides only).

4. **Open the studio beside the chat** right away, at the returned `studio_url`. In the Claude desktop
   app, use the built-in browser (`preview_start` with `url` set to the studio's origin, then `navigate`
   to the full URL). In Antigravity, use its browser. With no such pane, `open_studio(project_id)` opens
   the system browser.

5. **Write the script**: read `script_guide` (format, house style, writing for the ear), then call
   `write_script(project_id, segments)` with the whole script. Write from what the session actually
   found: real feature names, real behaviour, real numbers. Do not invent anything. If `errors` comes
   back, nothing was saved: fix and resend. Fix the `warnings` that matter.
   - Slides: one `slide` segment per slide, in order, narrating what the slide and its notes mean.
   - Live app: `step` segments with actions. Take selectors from the code you read, or from
     `inspect_page`, which shows a page's controls with ready-made selectors.

6. **Review**: summarise the script in chat (segment titles and a line of each narration, the estimated
   length) and point the user to the side panel, where they can edit any line, hear it in the voice
   (Preview) and approve. Apply changes they ask for in chat with `update_segment` or a new
   `write_script`; call `get_project` first, as they may have edited it in the studio. **Only call
   `approve_script` when the user explicitly approves in chat**; approving in the studio needs nothing
   from you.

7. **Web steps** (live app only): if it needs a login, `capture_login` (the user signs in themselves in
   the window that opens). Then `dry_run`; for each failure, look at its screenshot, fix the action with
   `update_segment` (use `inspect_page` for the right selector), and run it again until it passes.

8. **Render** once the script is approved: `render(project_id)` starts a background job; poll `get_job`
   now and then and report progress. Recording runs in real time. The result is an MP4 in the user's
   render folder, also playable on the studio's Render tab; reload the side panel to show it.

## Notes

- The script is spoken by a text-to-speech voice: no markdown, no URLs, spell out symbols and letters
  said one by one. `preview_voice(text)` returns a WAV for checking how a name is pronounced.
- Long waits in a live app (deploys, tests) get `wait_for` with `ff: true` and a short `what`, so the
  video fast-forwards them behind a banner.
- If the user asks for "a demo" and it is unclear whether they mean a video, ask before starting one.

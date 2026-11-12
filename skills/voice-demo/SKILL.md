---
name: voice-demo
description: >-
  Automate grounded, narrated 1080p demo and overview videos in Google Antigravity (and Claude Code) using the
  user's custom or standard Gemini TTS voice. Supports: (1) slides created in Antigravity + session context +
  user instructions, (2) user-provided slides (Google Slides, PDF, PPTX) + context + directions, and (3) live
  website walkthroughs (e.g. console.cloud.google.com) executed 100% inside Antigravity's built-in browser with
  interactive login onboarding, plus hybrid slide + live-website videos.
---

# Voice Demo Lab (Google Antigravity Plugin)

Voice Demo Lab automates high-quality 1080p narrated demo and overview videos completely orchestrated by **Google Antigravity** (primary) and compatible with Claude Code.

- **Plugin-only**: No standalone user CLI, no external Playwright browser windows.
- **Studio Sidecar Panel**: Always surface `[Voice Demo Studio](sidecar://custom-voice-demo-lab/studio/)` on its own line in chat so the user can open the Studio in Antigravity's auxiliary side pane with one click.
- **Gemini TTS speaks; you research & write**: Gemini TTS is used strictly for voice synthesis. You ground the script in authoritative technical docs, recent blogs/announcements, videos, slides, and live UI state.

---

## Supported Scenarios

| Scenario | Inputs | Visual Pipeline |
|---|---|---|
| **1. In-AGY Created Slides** (`scenario="slides"`) | Slides created in this AGY session (`gslides`, PDF, or PPTX) + AGY session context + user instructions | 2× supersampled Google Cloud title cards + 1080p slides |
| **2. User-Provided Slides** (`scenario="slides"`) | User's Google Slides URL/ID, `.pdf`, or `.pptx` + user context & directions | 2× supersampled title cards + 1080p slides + speaker notes |
| **3. Live Website Walkthrough** (`scenario="website"`) | Website URL (e.g. `https://console.cloud.google.com` or `localhost`) + user context & instructions | Title cards + 1080p live steps captured in Antigravity's built-in `browser` subagent |
| **4. Hybrid** (`scenario="hybrid"`) | Slides + live website URL + instructions | Title cards + slides + live AGY Browser walkthrough steps in one timeline |

---

## End-to-End Orchestration Workflow

### Step 1: Check Voice Setup (`get_settings`)
1. Call `get_settings()`.
2. If `setup_needed` is `true`:
   - Call `open_studio(page="setup", open_browser=False)`.
   - Output `[Voice Demo Studio](sidecar://custom-voice-demo-lab/studio/)` on its own line and ask the user to add their Gemini API key and choose a custom or standard narrator voice in the Studio side pane.
   - **STOP and wait** for the user to confirm setup is complete.
   - **Security invariant**: NEVER ask for, accept, repeat, or store a `GEMINI_API_KEY` in chat or tool calls—even if pasted by the user.
3. If the user asks for a specific saved voice ("use my formal voice", "switch to Kore"), check `list_voice_profiles()` and pass `voice_profile` to `start_demo` or call `use_voice_profile`.

---

### Step 2: Prepare Slide Decks (Scenarios 1, 2 & Hybrid)
- **Google Slides URL or Presentation ID** (`https://docs.google.com/presentation/d/<ID>/...`):
  - Preferred in Antigravity (uses your active `gslides` OAuth session so both crisp 1080p slide visuals AND speaker notes are captured):
    ```bash
    gslides readonly export <ID> <workspace_or_scratch>/deck.pdf --format pdf
    gslides readonly info <ID> --json > <workspace_or_scratch>/deck.gslides.json
    ```
  - Pass `decks=["/abs/path/deck.pdf"]` to `start_demo` (`sources.py` automatically ingests the sibling `.gslides.json` speaker notes!). You can also pass a Google Slides URL directly in `decks` when `gslides` CLI is authenticated globally.
- **Local `.pdf` or `.pptx`**: Pass absolute paths directly in `decks=[...]`.

---

### Step 3: Start the Demo Project (`start_demo`)
Call `start_demo`:
- `title`: Crisp title for the demo video.
- `goal`: 1–2 sentences stating what the viewer should walk away understanding.
- `brief`: Rich synthesis of what this AGY session built, analyzed, or discussed, plus user context.
- `scenario`: `"slides"`, `"website"`, or `"hybrid"`.
- `base_url`: Target website URL for `"website"` or `"hybrid"` demos (e.g. `"https://console.cloud.google.com"`).
- `decks`: List of exported `.pdf` / `.pptx` paths or Google Slides URLs.
- `audience` & `instructions`: User directions on tone, duration, target persona, and focus areas.

---

### Step 4: In-AGY Browser Login Onboarding (Mandatory First Step for Website & Hybrid Demos)
Whenever `base_url` is set (`scenario` is `"website"` or `"hybrid"`), **check login onboarding BEFORE exploring or capturing demo frames**:

1. **Invoke Antigravity's built-in `browser` subagent** (`invoke_subagent(TypeName="browser", Model="flash", ...)`):
   - Instruct it to navigate to `base_url` and check whether the user is already authenticated into the target app/console or whether a sign-in / SSO / account-chooser gate is shown.
   - Instruct it **NOT** to enter credentials—if a login gate appears, stop on that tab and report `LOGIN_REQUIRED` along with what sign-in page is visible.
   - If signed in, also inspect the landing view (navigation items, project/workspace name, visible features) so the script matches the real live UI!
2. **Handle the result**:
   - **If `LOGIN_REQUIRED`**:
     1. Call `record_web_auth(project_id, status="login_required", checked_url=base_url, notes="Waiting for user sign-in in AGY Browser pane")`.
     2. Ask the user in plain text to sign in directly inside the **Antigravity Browser pane** and reply once they are logged in.
     3. **STOP calling tools and wait** for the user's reply.
     4. Once the user confirms, resume the **same** `browser` subagent via `send_message(Recipient=browser_conv_id, ...)` to verify sign-in succeeded and inspect the authenticated landing state.
   - **If authenticated** (or once sign-in succeeds):
     - Call `record_web_auth(project_id, status="authenticated", checked_url=base_url, account_hint="<non-secret org/project label>")`.
   - **If public website requiring no login**:
     - Call `record_web_auth(project_id, status="not_needed", checked_url=base_url)`.

---

### Step 5: Research Reality (`demo-researcher` + `save_research`)
Every script must be rooted in verified technical reality—never guesswork:
1. Launch the bundled **`demo-researcher`** subagent (`invoke_subagent(TypeName="custom-voice-demo-lab:demo-researcher", ...)` or `search_web` + `read_file` directly for quick checks) with:
   - Slide digest & speaker notes from `start_demo`
   - Target website observations from Step 4
   - Session context & user instructions
2. Verify official documentation, API/CLI names, architecture details, recent Google Cloud / product blog announcements, release notes, and video references.
3. Persist the grounded research dossier into the project via **`save_research(project_id, summary, items)`**.

---

### Step 6: Author the Grounded Script (`script_guide` -> `write_script`)
1. Call `script_guide()` and follow its structure and TTS ear-writing rules:
   - Open with an intro `card`, use `slide` segments for deck visuals (synthesizing meaning + speaker notes + research rather than reading slide text verbatim), use `step` segments for live website interactions (`narration` + `actions` + `after_narration`), and close with a narrated recap `card`.
   - Populate `"citations"` on each segment referencing the `save_research` titles or slide numbers backing that segment.
   - Write natural spoken English: no markdown, no raw URLs, spell out numbers/versions naturally, expand acronyms on first use.
2. Call `write_script(project_id, segments)`. Fix any validation `errors` and address `warnings`.
3. Present a concise outline of the script (segment titles, estimated duration, key grounded sources) and place the Studio sidecar pill on its own line:

   [Voice Demo Studio](sidecar://custom-voice-demo-lab/studio/)

4. Ask the user to review, preview the voice, and click **Approve** (or **Approve & Render in AGY**) in Voice Demo Studio—or approve in chat.
   - Only call `approve_script(project_id, True)` yourself if the user explicitly approves in chat.

---

### Step 7: Capture Live Website Frames in Antigravity's Browser (`record_step_frames`)
For projects with `step` segments (either before or right after script approval, once login onboarding is `"authenticated"` or `"not_needed"`):
1. Send the step choreography to the authenticated Antigravity **`browser`** subagent (`send_message` to reuse the existing tab, or `invoke_subagent(TypeName="browser", Model="flash", ...)`):
   - For each `step` segment, have the `browser` subagent execute the step's `actions` on the live page (`goto`, `click`, `fill`, `hover`, `scroll`, `wait_for`) and capture clean 16:9 screenshots at key moments:
     - `"before"` / `"during"`: initial view or action in progress (shown during `narration`)
     - `"result"`: completed outcome on screen (shown during `after_narration`)
   - Verify the subagent's screenshots via `BROWSER_HOST_FACTS` / `read_file`.
2. Attach each step's screenshots via **`record_step_frames(project_id, segment_id, frames=[...])`**:
   ```json
   [
     {
       "path": "/abs/path/to/step1_before.png",
       "phase": "before",
       "caption": "Cloud Healthcare API library page"
     },
     {
       "path": "/abs/path/to/step1_result.png",
       "phase": "result",
       "caption": "FHIR R4 store active",
       "highlight": {"x": 0.18, "y": 0.28, "w": 0.52, "h": 0.22, "label": "FHIR R4 Store Active"},
       "zoom_to": {"x": 0.15, "y": 0.22, "w": 0.60, "h": 0.35}
     }
   ]
   ```
   - For long cloud/build waits (`ff: true`), set `"ff_what": "Provisioning FHIR dataset"` and `"ff_elapsed": 45` on the `"during"` frame to render an animated fast-forward HUD banner!

---

### Step 8: Readiness Check & Final Render (`check_demo_readiness` -> `render`)
1. Call `get_project(project_id)` first to pick up any line edits or pacing tweaks the user made in Voice Demo Studio.
2. Call `check_demo_readiness(project_id)` and resolve any `blockers` (unapproved script, missing step frames, unverified login).
3. Call `render(project_id, wait=True)` (or `wait=False` + `get_job` for very long videos).
4. Share the rendered `.mp4` clickable `file://` link and remind the user they can watch it directly in the **Render** tab of `[Voice Demo Studio](sidecar://custom-voice-demo-lab/studio/)`.

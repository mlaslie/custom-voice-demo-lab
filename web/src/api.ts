export type Scenario = "slides" | "website" | "hybrid";
export type Resolution = "1080p" | "4k";
export type SegType = "card" | "slide" | "step";
export type ActionOp =
  | "goto" | "click" | "fill" | "press" | "hover" | "scroll" | "wait" | "wait_for" | "highlight" | "unhighlight" | "verify";

declare global {
  interface Window {
    sidecar?: {
      conversationId?: string | null;
      agent?: {
        sendMessage: (message: string, convId?: string) => Promise<unknown>;
        startConversation: (message: string, title?: string) => Promise<unknown>;
      };
    };
  }
}

// Capture Antigravity Sidecar token on initial load so SPA route transitions keep authenticating writes.
const SIDECAR_TOKEN_KEY = "demolab_sidecar_token";
function resolveSidecarToken(): string {
  if (typeof window === "undefined") return "";
  const fromUrl = new URLSearchParams(window.location.search).get("token") || "";
  if (fromUrl) {
    try { sessionStorage.setItem(SIDECAR_TOKEN_KEY, fromUrl); } catch { /* ignore */ }
    return fromUrl;
  }
  try { return sessionStorage.getItem(SIDECAR_TOKEN_KEY) || ""; } catch { return ""; }
}
const INITIAL_SIDECAR_TOKEN = resolveSidecarToken();

export function inAntigravitySidecar(): boolean {
  if (typeof window === "undefined") return false;
  if (window.sidecar?.agent) return true;
  const sp = new URLSearchParams(window.location.search);
  return Boolean(INITIAL_SIDECAR_TOKEN || sp.get("conversationId"));
}

function withTokenQuery(url: string): string {
  const token = resolveSidecarToken() || INITIAL_SIDECAR_TOKEN;
  if (!token) return url;
  const sep = url.includes("?") ? "&" : "?";
  return `${url}${sep}token=${encodeURIComponent(token)}`;
}

export async function sendToAntigravity(message: string): Promise<boolean> {
  if (!window.sidecar?.agent) return false;
  if (window.sidecar.conversationId) {
    await window.sidecar.agent.sendMessage(message, window.sidecar.conversationId);
  } else {
    await window.sidecar.agent.startConversation(message, "Voice Demo Studio");
  }
  return true;
}

export interface Action {
  op: ActionOp;
  selector: string;
  target?: string;
  value: string;
  seconds: number;
  ff: boolean;
  what: string;
  label: string;
}

export interface HighlightBox {
  x: number;
  y: number;
  w: number;
  h: number;
  label: string;
}

export interface StepFrame {
  id: string;
  file: string;
  phase: "before" | "during" | "result";
  caption: string;
  highlight: HighlightBox | null;
  zoom_to: HighlightBox | null;
  ff_what: string;
  ff_elapsed: number;
}

export interface Segment {
  id: string;
  type: SegType;
  title: string;
  kicker: string;
  sub: string;
  bullets: string[];
  slide: number | null;
  narration: string;
  actions: Action[];
  actions_at: "during" | "after";
  after_narration: string;
  frames: StepFrame[];
  citations: string[];
  notes: string;
  approved: boolean;
}

export interface Source {
  id: string;
  kind: "url" | "repo" | "pptx" | "pdf" | "gslides" | "text" | "session";
  label: string;
  ref: string;
  text: string;
  slide_count: number;
  slide_offset: number;
  files: string[];
  images: string[];
}

export interface ResearchItem {
  id: string;
  title: string;
  source_type: "docs" | "blog" | "video" | "slide" | "webpage" | "code" | "context";
  url_or_path: string;
  summary: string;
  verified_claims: string[];
  added_at: number;
}

export interface WebAuth {
  status: "unchecked" | "authenticated" | "login_required" | "not_needed";
  checked_url: string;
  account_hint: string;
  notes: string;
  updated_at: number;
}

export interface Readiness {
  ready: boolean;
  blockers: string[];
  warnings: string[];
  voice_ready: boolean;
  script_approved: boolean;
  has_research: boolean;
  research_count: number;
  step_count: number;
  web_auth_status: WebAuth["status"];
  missing_step_frames: { segment_id: string; title: string }[];
}

export interface Check { segment_id: string; index: number; ok: boolean; error: string; shot: string }
export interface Render {
  file: string;
  created_at: number;
  seconds: number;
  segments: number;
  resolution?: Resolution;
  width?: number;
  height?: number;
  drive_file_id?: string;
  drive_url?: string;
  drive_folder?: string;
  drive_uploaded_at?: number;
}

export interface GDriveFolder {
  id: string;
  name: string;
  parent_id: string;
  shared?: boolean;
}

export interface GDriveStatus {
  status: "not_installed" | "disabled" | "needs_auth" | "connected";
  installed: boolean;
  disabled: boolean;
  connected: boolean;
  account_email: string;
  folders: GDriveFolder[];
  updated_at: number;
}

export interface Project {
  id: string;
  name: string;
  scenario: Scenario;
  base_url: string;
  goal: string;
  brief: string;
  audience: string;
  instructions: string;
  resolution: "" | Resolution;
  profile_id: string;
  speed: number;
  voice_id: string;
  voice_style: string;
  sources: Source[];
  research_summary: string;
  research: ResearchItem[];
  web_auth: WebAuth;
  segments: Segment[];
  slides: string[];
  script_approved: boolean;
  has_login: boolean;
  checks: Check[];
  renders: Render[];
  updated_at: number;
}

export interface ProjectSummary {
  id: string;
  name: string;
  scenario: Scenario;
  base_url: string;
  goal: string;
  resolution?: "" | Resolution;
  updated_at: number;
  script_approved: boolean;
  segments: number;
  renders: number;
  sources: number;
  research_count: number;
  web_auth_status: WebAuth["status"];
}

export interface ApiKey { id: string; name: string; hint: string; created_at: number }

export interface VoiceProfile {
  id: string;
  name: string;
  description: string;
  key_id: string;
  voice: string;
  voice_name: string;
  kind: "custom" | "standard";
  style: string;
  speed: number;
  verified_at: number;
  verify_error: string;
}

export interface Voice { id: string; name: string; kind: "custom" | "standard"; locale: string }
export interface KeyVoices {
  custom: Voice[]; standard: Voice[]; standard_total: number; multilingual: number;
  locales: { code: string; count: number }[];
}

export interface Settings {
  keys: ApiKey[];
  profiles: VoiceProfile[];
  active_profile: string;
  active: VoiceProfile | null;
  setup_needed: boolean;
  key_source: "env" | "keychain";
  tts_model: string;
  output_dir: string;
  default_resolution: Resolution;
  audience: string;
  fake_gemini: boolean;
}

export interface PreviewWith { project_id?: string; profile_id?: string; key_id?: string; voice?: string; style?: string; speed?: number }

export interface Job {
  id: string; project_id: string; kind: string; state: "running" | "done" | "error"; progress: number;
  message: string; log: string[]; result: Record<string, unknown> | null; error: string;
}

function authHeaders(extra?: Record<string, string>): Record<string, string> {
  const token = resolveSidecarToken() || INITIAL_SIDECAR_TOKEN;
  const h: Record<string, string> = { ...(extra || {}) };
  if (token) h["X-Sidecar-Token"] = token;
  return h;
}

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: authHeaders() };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.body = JSON.stringify(body);
    init.headers = authHeaders({ "Content-Type": "application/json" });
  }
  const r = await fetch(withTokenQuery(path), init);
  if (!r.ok) {
    let msg = `${r.status} ${r.statusText}`;
    try { msg = (await r.json()).detail ?? msg; } catch { /* not json */ }
    const d = msg as unknown as { errors?: string[] };
    throw new Error(typeof msg === "string" ? msg : d.errors ? d.errors.join("\n") : JSON.stringify(msg));
  }
  return r.headers.get("content-type")?.includes("json") ? r.json() : (r.blob() as Promise<T>);
}

export const api = {
  settings: () => req<Settings>("GET", "/api/settings"),
  saveSettings: (s: Partial<Settings>) => req<Settings>("PUT", "/api/settings", s),
  models: () => req<{ name: string; display?: string; methods: string[] }[]>("GET", "/api/models"),
  preview: (text: string, w: PreviewWith = {}) => req<Blob>("POST", "/api/voice/preview", { text, ...w }),
  testClip: async (text: string, w: PreviewWith) => {
    const r = await fetch(withTokenQuery("/api/voice/preview"), {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify({ text, ...w }),
    });
    if (!r.ok) { let m = `${r.status}`; try { m = (await r.json()).detail ?? m; } catch { /* not json */ } throw new Error(m); }
    return { blob: await r.blob(), seconds: Number(r.headers.get("X-Seconds")), wpm: Number(r.headers.get("X-Words-Per-Minute")) };
  },
  addKey: (name: string, key: string) =>
    req<{ key: ApiKey; custom_voices: number; settings: Settings }>("POST", "/api/keys", { name, key }),
  deleteKey: (id: string) => req<Settings>("DELETE", `/api/keys/${id}`),
  keyVoices: (id: string, locale = "", q = "") =>
    req<KeyVoices>("GET", `/api/keys/${id}/voices?locale=${encodeURIComponent(locale)}&q=${encodeURIComponent(q)}`),
  addProfile: (b: Omit<VoiceProfile, "id" | "verified_at" | "verify_error" | "speed"> & { speed?: number; activate?: boolean }) => req<Settings>("POST", "/api/profiles", b),
  patchProfile: (id: string, b: Partial<VoiceProfile>) => req<Settings>("PATCH", `/api/profiles/${id}`, b),
  deleteProfile: (id: string) => req<Settings>("DELETE", `/api/profiles/${id}`),
  activateProfile: (id: string) => req<Settings>("POST", `/api/profiles/${id}/activate`),
  verifyProfile: (id: string) => req<{ ok: boolean; error: string; settings: Settings }>("POST", `/api/profiles/${id}/verify`),

  projects: () => req<ProjectSummary[]>("GET", "/api/projects"),
  project: (id: string) => req<Project>("GET", `/api/projects/${id}`),
  patchProject: (id: string, b: Partial<Project>) => req<Project>("PATCH", `/api/projects/${id}`, b),
  deleteProject: (id: string) => req("DELETE", `/api/projects/${id}`),

  putSegments: (id: string, segs: Segment[]) =>
    req<{ project: Project; warnings: string[]; seconds: number }>("PUT", `/api/projects/${id}/segments`, segs),
  patchSegment: (id: string, sid: string, b: Partial<Segment>) =>
    req<Project>("PATCH", `/api/projects/${id}/segments/${sid}`, b),
  approve: (id: string, approved: boolean) => req<Project>("POST", `/api/projects/${id}/approve`, { approved }),

  setWebAuth: (id: string, status: WebAuth["status"], account_hint = "", notes = "") =>
    req<Project>("POST", `/api/projects/${id}/web-auth`, { status, account_hint, notes }),
  forgetLogin: (id: string) => req<Project>("DELETE", `/api/projects/${id}/login`),
  readiness: (id: string) => req<Readiness>("GET", `/api/projects/${id}/readiness`),

  render: (id: string, force = false, resolution: "" | Resolution = "") =>
    req<Job>("POST", `/api/projects/${id}/render`, { force, resolution }),
  jobs: (id: string) => req<Job[]>("GET", `/api/projects/${id}/jobs`),
  job: (jid: string) => req<Job>("GET", `/api/jobs/${jid}`),
  reveal: (id: string, i: number, downloaded = false) =>
    req<{ file: string }>("POST", `/api/projects/${id}/renders/${i}/reveal${downloaded ? "?downloaded=true" : ""}`),
  downloadLocal: (
    id: string,
    i: number,
    opts: { dest_dir?: string; dest_file?: string; choose_location?: boolean } = { choose_location: true },
  ) =>
    req<{ canceled: boolean; saved_to: string; filename: string }>(
      "POST",
      `/api/projects/${id}/renders/${i}/download`,
      opts,
    ),
  patchRender: (id: string, i: number, b: { drive_file_id?: string; drive_url?: string; drive_folder?: string }) =>
    req<Project>("PATCH", `/api/projects/${id}/renders/${i}`, b),
  gdriveStatus: () => req<GDriveStatus>("GET", "/api/gdrive/status"),
};

export const slideUrl = (pid: string, n: number) => withTokenQuery(`/api/projects/${pid}/slides/${n}`);
export const frameUrl = (pid: string, name: string) => withTokenQuery(`/api/projects/${pid}/frames/${encodeURIComponent(name)}`);
export const checkUrl = (pid: string, name: string) => withTokenQuery(`/api/projects/${pid}/checks/${encodeURIComponent(name)}`);
export const videoUrl = (pid: string, i: number) => withTokenQuery(`/api/projects/${pid}/renders/${i}/video`);
export const videoDownloadUrl = (pid: string, i: number) => withTokenQuery(`/api/projects/${pid}/renders/${i}/video?download=1`);

export const newAction = (op: ActionOp = "click"): Action =>
  ({ op, selector: "", target: "", value: "", seconds: 0, ff: false, what: "", label: "" });

export const newSegment = (type: SegType): Segment => ({
  id: "seg_" + Math.random().toString(16).slice(2, 12),
  type,
  title: "",
  kicker: "",
  sub: "",
  bullets: [],
  slide: type === "slide" ? 0 : null,
  narration: "",
  actions: [],
  actions_at: "during",
  after_narration: "",
  frames: [],
  citations: [],
  notes: "",
  approved: false,
});

/** ~130 words per minute at 1.0x over a whole video (pauses included). */
export const speakSeconds = (text: string, speed = 1) => (text.trim() ? text.trim().split(/\s+/).length / 2.2 / speed : 0);

let regionNames: Intl.DisplayNames | null = null;
try {
  if (typeof Intl !== "undefined" && "DisplayNames" in Intl) {
    regionNames = new Intl.DisplayNames(["en"], { type: "language" });
  }
} catch {
  regionNames = null;
}

export function localeName(code: string): string {
  if (!code) return "Multilingual";
  const [lang, region = ""] = code.split("-");
  try { return regionNames?.of(`${lang}-${region.toUpperCase()}`) ?? code; } catch { return code; }
}

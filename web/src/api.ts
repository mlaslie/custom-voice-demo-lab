export type SegType = "card" | "slide" | "step";
export type ActionOp =
  | "goto" | "click" | "fill" | "press" | "hover" | "scroll" | "wait" | "wait_for" | "highlight" | "unhighlight";

export interface Action {
  op: ActionOp;
  selector: string;
  value: string;
  seconds: number;
  ff: boolean;
  what: string;
  label: string;
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

export interface Check { segment_id: string; index: number; ok: boolean; error: string; shot: string }
export interface Render { file: string; created_at: number; seconds: number; segments: number }

export interface Project {
  id: string;
  name: string;
  base_url: string;
  goal: string;
  brief: string;
  audience: string;
  instructions: string;
  profile_id: string;
  speed: number;
  voice_id: string;
  voice_style: string;
  sources: Source[];
  segments: Segment[];
  slides: string[];
  script_approved: boolean;
  has_login: boolean;
  checks: Check[];
  renders: Render[];
  updated_at: number;
}

export interface ProjectSummary {
  id: string; name: string; base_url: string; goal: string; updated_at: number; script_approved: boolean;
  segments: number; renders: number; sources: number;
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
  audience: string;
  fake_gemini: boolean;
}

/** What a preview speaks with: a project's voice, a saved profile, or any voice with a saved key. */
export interface PreviewWith { project_id?: string; profile_id?: string; key_id?: string; voice?: string; style?: string; speed?: number }

export interface Job {
  id: string; project_id: string; kind: string; state: "running" | "done" | "error"; progress: number;
  message: string; log: string[]; result: Record<string, unknown> | null; error: string;
}

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method };
  if (body instanceof FormData) init.body = body;
  else if (body !== undefined) {
    init.body = JSON.stringify(body);
    init.headers = { "Content-Type": "application/json" };
  }
  const r = await fetch(path, init);
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
  /** A test clip plus its measured length and pace. */
  testClip: async (text: string, w: PreviewWith) => {
    const r = await fetch("/api/voice/preview", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text, ...w }) });
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

  dryrun: (id: string) => req<Job>("POST", `/api/projects/${id}/dryrun`),
  login: (id: string) => req<Job>("POST", `/api/projects/${id}/login`, {}),
  forgetLogin: (id: string) => req<Project>("DELETE", `/api/projects/${id}/login`),
  render: (id: string, force = false) => req<Job>("POST", `/api/projects/${id}/render`, { force }),
  jobs: (id: string) => req<Job[]>("GET", `/api/projects/${id}/jobs`),
  job: (jid: string) => req<Job>("GET", `/api/jobs/${jid}`),
  reveal: (id: string, i: number) => req("POST", `/api/projects/${id}/renders/${i}/reveal`),
};

export const slideUrl = (pid: string, n: number) => `/api/projects/${pid}/slides/${n}`;
export const checkUrl = (pid: string, name: string) => `/api/projects/${pid}/checks/${name}`;
export const videoUrl = (pid: string, i: number) => `/api/projects/${pid}/renders/${i}/video`;

export const newAction = (op: ActionOp = "click"): Action =>
  ({ op, selector: "", value: "", seconds: 0, ff: false, what: "", label: "" });

export const newSegment = (type: SegType): Segment => ({
  id: "seg_" + Math.random().toString(16).slice(2, 12), type, title: "", kicker: "", sub: "", bullets: [],
  slide: type === "slide" ? 0 : null, narration: "", actions: [], actions_at: "during", after_narration: "",
  notes: "", approved: false,
});

/** ~130 words per minute at 1.0x over a whole video (pauses included), measured on the approved narrator style. */
export const speakSeconds = (text: string, speed = 1) => (text.trim() ? text.trim().split(/\s+/).length / 2.2 / speed : 0);

const regionNames = typeof Intl !== "undefined" && "DisplayNames" in Intl
  ? new Intl.DisplayNames(undefined, { type: "language" }) : null;

/** "en-us" -> "English (United States)", "es-419" -> "Spanish (Latin America)". */
export function localeName(code: string): string {
  if (!code) return "Multilingual";
  const [lang, region = ""] = code.split("-");
  try { return regionNames?.of(`${lang}-${region.toUpperCase()}`) ?? code; } catch { return code; }
}

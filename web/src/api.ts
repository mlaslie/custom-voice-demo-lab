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
  instructions: string;
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

export interface Settings {
  voice_id: string;
  voice_style: string;
  tts_model: string;
  script_model: string;
  output_dir: string;
  google_client_secret: string;
  audience: string;
  gemini_key_set: boolean;
  gemini_key_source: "env" | "keychain" | null;
  google_connected: boolean;
  fake_gemini: boolean;
}

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
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return r.headers.get("content-type")?.includes("json") ? r.json() : (r.blob() as Promise<T>);
}

export const api = {
  settings: () => req<Settings>("GET", "/api/settings"),
  saveSettings: (s: Partial<Settings>) => req<Settings>("PUT", "/api/settings", s),
  setKey: (key: string) => req<Settings>("PUT", "/api/settings/gemini-key", { key }),
  clearKey: () => req<Settings>("DELETE", "/api/settings/gemini-key"),
  models: () => req<{ name: string; display?: string; methods: string[] }[]>("GET", "/api/models"),
  preview: (text: string, project_id?: string) => req<Blob>("POST", "/api/voice/preview", { text, project_id }),
  googleConnect: () => req<{ state: string }>("POST", "/api/google/connect"),
  googleStatus: () => req<{ state: string; error: string; connected: boolean }>("GET", "/api/google/status"),
  googleDisconnect: () => req("DELETE", "/api/google"),

  projects: () => req<ProjectSummary[]>("GET", "/api/projects"),
  createProject: (b: { name: string; base_url?: string; goal?: string; instructions?: string }) =>
    req<Project>("POST", "/api/projects", b),
  project: (id: string) => req<Project>("GET", `/api/projects/${id}`),
  patchProject: (id: string, b: Partial<Project>) => req<Project>("PATCH", `/api/projects/${id}`, b),
  deleteProject: (id: string) => req("DELETE", `/api/projects/${id}`),

  addSource: (id: string, b: { kind: string; ref?: string; text?: string; label?: string; files?: string[] }) =>
    req<Project>("POST", `/api/projects/${id}/sources`, b),
  upload: (id: string, file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return req<Project>("POST", `/api/projects/${id}/sources/upload`, fd);
  },
  deleteSource: (id: string, sid: string) => req<Project>("DELETE", `/api/projects/${id}/sources/${sid}`),

  draft: (id: string) => req<Job>("POST", `/api/projects/${id}/script/draft`),
  putSegments: (id: string, segs: Segment[]) => req<Project>("PUT", `/api/projects/${id}/segments`, segs),
  patchSegment: (id: string, sid: string, b: Partial<Segment>) =>
    req<Project>("PATCH", `/api/projects/${id}/segments/${sid}`, b),
  revise: (id: string, sid: string, instruction: string) =>
    req<Project>("POST", `/api/projects/${id}/segments/${sid}/revise`, { instruction }),
  approve: (id: string, approved: boolean) => req<Project>("POST", `/api/projects/${id}/approve`, { approved }),

  explore: (id: string, segment_ids?: string[]) => req<Job>("POST", `/api/projects/${id}/explore`, { segment_ids }),
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

/** ~156 words per minute, the pace of the approved narrator style. */
export const speakSeconds = (text: string) => (text.trim() ? text.trim().split(/\s+/).length / 2.6 : 0);

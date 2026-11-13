import {
  AlertTriangle,
  BookOpenCheck,
  CloudUpload,
  Download,
  ExternalLink,
  Film,
  FolderOpen,
  Layers,
  Play,
  Presentation,
  Search,
  Sparkles,
  Trash2,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  api,
  inAntigravitySidecar,
  sendToAntigravity,
  videoUrl,
  type GDriveStatus,
  type ProjectSummary,
  type RenderDetail,
  type Scenario,
  type Settings,
} from "../api";
import { ConfirmDialog } from "../components/ConfirmDialog";
import DriveFolderModal, { type DriveDestination } from "../components/DriveFolderModal";
import { Alert, Badge, Button, Empty } from "../components/ui";

const SCENARIO_BADGE: Record<Scenario, { label: string; tone: "blue" | "amber" | "violet" }> = {
  slides: { label: "Slides", tone: "blue" },
  website: { label: "Live Web", tone: "amber" },
  hybrid: { label: "Hybrid", tone: "violet" },
};

type ResFilter = "all" | "4k" | "1080p";

const DRIVE_FOLDER_ID_KEY = "demolab_drive_folder_id";
function loadSavedDriveFolderId(): string {
  try {
    return localStorage.getItem(DRIVE_FOLDER_ID_KEY) || "root";
  } catch {
    return "root";
  }
}
function saveDriveFolderId(v: string) {
  try {
    localStorage.setItem(DRIVE_FOLDER_ID_KEY, v || "root");
  } catch {
    /* ignore */
  }
}

function formatDuration(secs: number): string {
  const s = Math.max(0, Math.round(secs));
  return `${Math.floor(s / 60)}m ${String(s % 60).padStart(2, "0")}s`;
}

function formatMiB(bytes?: number): string {
  if (!bytes || bytes <= 0) return "";
  return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
}

export default function Projects({ settings }: { settings: Settings | null }) {
  const [list, setList] = useState<ProjectSummary[] | null>(null);
  const [gdrive, setGdrive] = useState<GDriveStatus | null>(null);
  const [query, setQuery] = useState("");
  const [resFilter, setResFilter] = useState<ResFilter>("all");
  const [playingKey, setPlayingKey] = useState("");
  const [err, setErr] = useState("");
  const [toast, setToast] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);
  const [driveTarget, setDriveTarget] = useState<{ project: ProjectSummary; render: RenderDetail } | null>(null);
  const [driveBusy, setDriveBusy] = useState(false);
  const [refreshingFolders, setRefreshingFolders] = useState(false);

  const load = useCallback(() => {
    api.projects().then((res) => { setList(res); setErr(""); }).catch((e) => setErr(e.message));
  }, []);

  const refreshGdrive = useCallback(() => {
    api.gdriveStatus().then(setGdrive).catch(() => {});
  }, []);

  useEffect(() => {
    load();
    refreshGdrive();
    const id = setInterval(() => {
      if (document.visibilityState === "visible") {
        load();
        refreshGdrive();
      }
    }, 4000);
    return () => clearInterval(id);
  }, [load, refreshGdrive]);

  useEffect(() => {
    setRefreshingFolders(false);
  }, [gdrive?.updated_at]);

  const showToast = (msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast((cur) => (cur === msg ? "" : cur)), 4000);
  };

  const askAgy = async (prompt: string) => {
    await sendToAntigravity(prompt);
    showToast("Sent prompt to Antigravity chat.");
  };

  const filtered = useMemo(() => {
    if (!list) return null;
    const q = query.trim().toLowerCase();
    return list.filter((p) => {
      const renders = p.renders_detail ?? [];
      if (resFilter !== "all") {
        const hasRes = renders.some((r) => (r.resolution || "1080p") === resFilter);
        if (!hasRes) return false;
      }
      if (!q) return true;
      const hay = `${p.name} ${p.goal} ${p.base_url} ${renders.map((r) => r.file).join(" ")}`.toLowerCase();
      return hay.includes(q);
    });
  }, [list, query, resFilter]);

  const handleSaveAs = async (projectId: string, renderIdx: number) => {
    setErr("");
    try {
      const out = await api.downloadLocal(projectId, renderIdx, { choose_location: true });
      if (!out.canceled && out.saved_to) {
        showToast(`Saved MP4 to ${out.saved_to}`);
      }
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  const handleDriveClick = async (project: ProjectSummary, render: RenderDetail) => {
    setErr("");
    if (gdrive?.connected) {
      setDriveTarget({ project, render });
      return;
    }
    const status = gdrive?.status ?? "not_installed";
    const prompt =
      status === "not_installed"
        ? `Please install and connect the official Google Drive (gdrive) plugin in Antigravity so I can push rendered videos from Voice Demo Studio, then sync Drive folders via sync_gdrive_state.`
        : status === "disabled"
          ? `The Google Drive (gdrive) plugin is disabled in Antigravity. Please share its link so I can enable it, then sync folders via sync_gdrive_state.`
          : `Please verify my Google Drive (gdrive) sign-in in Antigravity and sync Drive folders via \`gdrive readonly search --type folder --max 400 --json\` + \`sync_gdrive_state\`.`;
    const sent = await sendToAntigravity(prompt);
    if (!sent) {
      setErr("Open Voice Demo Studio inside Google Antigravity to upload directly to Google Drive.");
      return;
    }
    showToast("Check Antigravity chat to connect Google Drive and load folders.");
  };

  const handleRefreshFolders = async () => {
    setRefreshingFolders(true);
    const sent = await sendToAntigravity(
      `Refresh my Google Drive folder list for Voice Demo Studio: run \`gdrive readonly search --type folder --max 400 --json\` ` +
        `and persist via \`sync_gdrive_state\`.`,
    );
    if (!sent) {
      setRefreshingFolders(false);
      setErr("Open Voice Demo Studio inside Google Antigravity to refresh Google Drive folders.");
    }
  };

  const handleConfirmDriveUpload = async (dest: DriveDestination) => {
    if (!driveTarget) return;
    setDriveBusy(true);
    setErr("");
    try {
      saveDriveFolderId(dest.folderId);
      const { project, render } = driveTarget;
      const targetDesc =
        dest.folderId === "root" && !dest.newSubfolder
          ? `into My Drive root (folder_id="root")`
          : dest.newSubfolder
            ? `by creating subfolder "${dest.newSubfolder}" inside folder_id="${dest.folderId}" ("${dest.folderPath}")`
            : `into Google Drive folder "${dest.folderPath}" (folder_id="${dest.folderId}")`;
      const prompt =
        `Upload rendered MP4 #${render.index} ("${render.file}") for Voice Demo Lab project "${project.name}" (${project.id}) ` +
        `${targetDesc} using the official Google Drive (gdrive) plugin, then record the URL and folder via ` +
        `record_render_drive_upload (project_id="${project.id}", render_index=${render.index}).`;
      const sent = await sendToAntigravity(prompt);
      if (!sent) {
        throw new Error("Open Voice Demo Studio inside Google Antigravity to push to Google Drive.");
      }
      setDriveTarget(null);
      showToast("Started Google Drive upload in Antigravity.");
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setDriveBusy(false);
    }
  };

  const voiceLabel = (profileId?: string) =>
    settings?.profiles.find((v) => v.id === profileId)?.name || settings?.active?.name || "Default voice";

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Projects &amp; Generated Videos</h1>
          <p className="mt-0.5 text-xs text-zinc-500">
            Browse completed 1080p and 4K videos, play previews, inspect scripts, save locally, or push to Google Drive.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-zinc-400" />
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search videos or topics…"
              aria-label="Filter generated video projects"
              autoCorrect="off"
              autoCapitalize="none"
              spellCheck={false}
              className="input w-48 !py-1.5 !pl-8 text-xs sm:w-56"
            />
          </div>

          <div
            className="inline-flex rounded-lg border border-zinc-200 bg-white p-0.5 dark:border-zinc-800 dark:bg-zinc-900"
            role="group"
            aria-label="Filter by resolution"
          >
            {(["all", "4k", "1080p"] as const).map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => setResFilter(r)}
                className={`rounded-md px-2.5 py-1 text-xs font-medium transition ${
                  resFilter === r
                    ? "bg-brand-600 text-white shadow-sm"
                    : "text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
                }`}
              >
                {r === "all" ? "All" : r === "4k" ? "4K" : "1080p"}
              </button>
            ))}
          </div>
        </div>
      </div>

      {settings?.setup_needed && (
        <Alert tone="amber">
          <div className="flex items-center gap-2">
            <AlertTriangle className="size-4 shrink-0" />
            <span>
              Add an AI Studio API key in{" "}
              <Link className="font-semibold underline" to="/auth">
                Auth
              </Link>{" "}
              and configure a voice in{" "}
              <Link className="font-semibold underline" to="/voice-lab">
                Voice Lab
              </Link>{" "}
              before drafting or rendering.
            </span>
          </div>
        </Alert>
      )}
      {toast && <Alert tone="blue">{toast}</Alert>}
      {err && <Alert>{err}</Alert>}

      {list && list.length === 0 && (
        <Empty icon={<Presentation className="size-6" />} title="No generated demos yet">
          <p>Ask Antigravity in chat to create a grounded narrated demo from slides or a live website.</p>
          {inAntigravitySidecar() && (
            <div className="mt-4 flex justify-center">
              <Button
                variant="primary"
                size="sm"
                icon={<Sparkles className="size-3.5" />}
                onClick={() => askAgy("Create a narrated demo video from the slides in this session using Voice Demo Lab.")}
              >
                Start Slide Demo in AGY
              </Button>
            </div>
          )}
        </Empty>
      )}

      {filtered && filtered.length === 0 && list && list.length > 0 && (
        <div className="card p-6 text-center text-xs text-zinc-500">
          No projects match the current filter.
        </div>
      )}

      <div className="grid gap-3 md:grid-cols-2">
        {filtered?.map((p) => {
          const scen = SCENARIO_BADGE[p.scenario || "slides"] ?? SCENARIO_BADGE.slides;
          const allRenders = [...(p.renders_detail ?? [])].reverse();
          const shownRenders =
            resFilter === "all"
              ? allRenders
              : allRenders.filter((r) => (r.resolution || "1080p") === resFilter);

          return (
            <article key={p.id} className="card flex flex-col gap-3 p-4">
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <Link
                    to={`/projects/${p.id}`}
                    className="block truncate text-sm font-semibold leading-snug hover:text-brand-600 dark:hover:text-brand-400"
                  >
                    {p.name}
                  </Link>
                  <p className="mt-0.5 truncate text-xs text-zinc-500">
                    {p.segments} segment{p.segments === 1 ? "" : "s"} · Voice: {voiceLabel(p.profile_id)}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  <Badge tone={scen.tone}>{scen.label}</Badge>
                  <button
                    type="button"
                    onClick={() => setDeleteTarget({ id: p.id, name: p.name })}
                    className="rounded-md p-1 text-zinc-400 transition hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-950/40"
                    title="Delete project"
                    aria-label={`Delete ${p.name}`}
                  >
                    <Trash2 className="size-4" />
                  </button>
                </div>
              </div>

              {shownRenders.length > 0 ? (
                <div className="space-y-2">
                  {shownRenders.map((r) => {
                    const key = `${p.id}:${r.index}`;
                    const isPlaying = playingKey === key;
                    const fname = r.file.split("/").pop() || `${p.id}.mp4`;
                    const is4k = (r.resolution || "1080p") === "4k";
                    const dims = `${r.width || (is4k ? 3840 : 1920)}×${r.height || (is4k ? 2160 : 1080)}`;
                    const sizeText = formatMiB(r.size_bytes);

                    return (
                      <div
                        key={key}
                        className="space-y-2 rounded-xl border border-zinc-200 bg-zinc-50/70 p-2.5 dark:border-zinc-800 dark:bg-zinc-950"
                      >
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="min-w-0 space-y-0.5">
                            <div className="flex flex-wrap items-center gap-2">
                              <span
                                className={`text-xs font-semibold ${
                                  is4k ? "text-brand-600 dark:text-brand-400" : "text-zinc-800 dark:text-zinc-200"
                                }`}
                              >
                                {is4k ? "4K" : "1080p"} · {dims}
                              </span>
                              <span className="text-xs text-zinc-500">
                                {formatDuration(r.seconds)}
                                {sizeText ? ` · ${sizeText}` : ""}
                              </span>
                              {r.drive_url && (
                                <span className="text-xs font-medium text-emerald-600 dark:text-emerald-400">
                                  Synced to Drive
                                </span>
                              )}
                            </div>
                            <div className="truncate font-mono text-xs text-zinc-500" title={r.file}>
                              {fname}
                            </div>
                          </div>

                          <div className="flex flex-wrap items-center gap-1.5">
                            <button
                              type="button"
                              onClick={() => setPlayingKey(isPlaying ? "" : key)}
                              className="inline-flex items-center gap-1 rounded-lg border border-zinc-300 bg-white px-2.5 py-1 text-xs font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
                            >
                              <Play className="size-3" /> {isPlaying ? "Hide" : "Play"}
                            </button>
                            <button
                              type="button"
                              onClick={() => handleSaveAs(p.id, r.index)}
                              className="inline-flex items-center gap-1 rounded-lg border border-zinc-300 bg-white px-2.5 py-1 text-xs font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200"
                            >
                              <Download className="size-3" /> Save As
                            </button>
                            {r.drive_url ? (
                              <a
                                href={r.drive_url}
                                target="_blank"
                                rel="noreferrer"
                                className="inline-flex items-center gap-1 rounded-lg border border-emerald-300 bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-800 hover:bg-emerald-100 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200"
                              >
                                <ExternalLink className="size-3" /> Drive
                              </a>
                            ) : (
                              inAntigravitySidecar() && (
                                <button
                                  type="button"
                                  onClick={() => handleDriveClick(p, r)}
                                  className="inline-flex items-center gap-1 rounded-lg bg-brand-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-brand-700"
                                >
                                  <CloudUpload className="size-3" /> Drive
                                </button>
                              )
                            )}
                            <button
                              type="button"
                              onClick={() => api.reveal(p.id, r.index)}
                              className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs text-zinc-500 hover:bg-zinc-200/70 dark:hover:bg-zinc-800"
                              title="Show in Finder"
                              aria-label="Show in Finder"
                            >
                              <FolderOpen className="size-3.5" />
                            </button>
                          </div>
                        </div>

                        {isPlaying && (
                          <video
                            src={videoUrl(p.id, r.index)}
                            controls
                            autoPlay
                            className="aspect-video w-full rounded-lg bg-black"
                          />
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="rounded-xl border border-dashed border-zinc-200 p-3 text-xs text-zinc-500 dark:border-zinc-800">
                  No MP4 rendered yet.{" "}
                  <Link to={`/projects/${p.id}?tab=render`} className="font-medium text-brand-600 underline dark:text-brand-400">
                    Open Render tab
                  </Link>
                </div>
              )}

              <div className="mt-auto flex flex-wrap items-center justify-between gap-2 pt-1 text-xs text-zinc-500">
                <div className="flex items-center gap-2.5">
                  {p.script_approved ? <Badge tone="green">Approved</Badge> : p.segments ? <Badge tone="amber">In review</Badge> : <Badge>Draft</Badge>}
                  <span className="inline-flex items-center gap-1"><Layers className="size-3.5" />{p.segments}</span>
                  {p.research_count > 0 && (
                    <span className="inline-flex items-center gap-1 text-emerald-600 dark:text-emerald-400">
                      <BookOpenCheck className="size-3.5" />{p.research_count}
                    </span>
                  )}
                  <span className="inline-flex items-center gap-1"><Film className="size-3.5" />{p.renders}</span>
                </div>
                <Link
                  to={`/projects/${p.id}`}
                  className="font-medium text-brand-600 hover:underline dark:text-brand-400"
                >
                  Open Workspace →
                </Link>
              </div>
            </article>
          );
        })}
      </div>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="Delete project"
        body={`Delete "${deleteTarget?.name || ""}"? Its script, slides, and audio cache are removed; rendered MP4 videos remain on disk.`}
        confirmLabel="Delete Project"
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (!deleteTarget) return;
          const id = deleteTarget.id;
          api.deleteProject(id).then(() => {
            setDeleteTarget(null);
            load();
          }).catch((e) => setErr((e as Error).message));
        }}
      />

      {driveTarget && (
        <DriveFolderModal
          open={Boolean(driveTarget && gdrive?.connected)}
          accountEmail={gdrive?.account_email || ""}
          folders={gdrive?.folders || []}
          filename={driveTarget.render.file.split("/").pop() || `${driveTarget.project.id}.mp4`}
          busy={driveBusy}
          refreshing={refreshingFolders}
          initialFolderId={loadSavedDriveFolderId()}
          onClose={() => setDriveTarget(null)}
          onRefreshFolders={handleRefreshFolders}
          onConfirm={handleConfirmDriveUpload}
        />
      )}
    </div>
  );
}

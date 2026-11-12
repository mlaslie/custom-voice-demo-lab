import {
  AlertTriangle,
  CheckCircle2,
  Circle,
  Clapperboard,
  CloudUpload,
  Download,
  ExternalLink,
  FolderOpen,
  LogIn,
  PlugZap,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  api,
  inAntigravitySidecar,
  sendToAntigravity,
  videoUrl,
  type GDriveStatus,
  type Readiness,
  type Render,
  type Settings,
} from "../../api";
import DriveFolderModal, { type DriveDestination } from "../../components/DriveFolderModal";
import { JobStatus, useJob } from "../../components/hooks";
import { Alert, Badge, Button } from "../../components/ui";
import type { TabProps } from "../Project";

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

export default function RenderTab({ project: p, setProject, refresh, goto }: TabProps) {
  const [s, setS] = useState<Settings | null>(null);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [gdrive, setGdrive] = useState<GDriveStatus | null>(null);
  const [err, setErr] = useState("");
  const activeRes: "1080p" | "4k" = p.resolution || s?.default_resolution || "1080p";
  const changeResolution = (resolution: "1080p" | "4k") => {
    setErr("");
    api.patchProject(p.id, { resolution }).then(setProject).catch((e) => setErr(e.message));
  };
  const job = useJob(() => {
    refresh();
    api.readiness(p.id).then(setReadiness).catch(() => {});
  });

  const refreshGdrive = useCallback(() => {
    api.gdriveStatus().then(setGdrive).catch(() => {});
  }, []);

  useEffect(() => {
    api.settings().then(setS).catch(() => {});
  }, []);
  useEffect(() => {
    api.readiness(p.id).then(setReadiness).catch(() => {});
  }, [p]);
  useEffect(() => {
    refreshGdrive();
    const timer = window.setInterval(refreshGdrive, 3500);
    return () => window.clearInterval(timer);
  }, [refreshGdrive]);
  useEffect(() => {
    api.jobs(p.id).then((js) => {
      const r = js.find((j) => j.kind === "render" && j.state === "running");
      if (r) job.start(Promise.resolve(r));
    });
  }, [p.id]);

  const steps = p.segments.filter((x) => x.type === "step");
  const authOk =
    p.web_auth?.status === "authenticated" || p.web_auth?.status === "not_needed" || p.has_login;
  const checks = [
    {
      ok: !!s && !s.setup_needed,
      label: `Narrator voice: ${s?.profiles.find((v) => v.id === p.profile_id)?.name ?? s?.active?.name ?? "none"}`,
      fix: <Link className="underline" to="/setup">Setup</Link>,
    },
    {
      ok: (p.research?.length ?? 0) > 0 || Boolean(p.research_summary?.trim()),
      label: `Grounded technical research (${p.research?.length ?? 0} sources)`,
      soft: true,
    },
    {
      ok: p.segments.length > 0,
      label: "Script drafted",
      fix: <button className="underline" onClick={() => goto("script")}>Script</button>,
    },
    {
      ok: p.script_approved,
      label: "Script approved",
      fix: <button className="underline" onClick={() => goto("script")}>Approve on Script tab</button>,
    },
    ...(steps.length
      ? [
          {
            ok: authOk,
            label: `AGY Browser login verified (${p.web_auth?.status || "unchecked"})`,
            fix: <button className="underline" onClick={() => goto("rehearse")}>AGY Browser tab</button>,
            soft: true,
          },
          {
            ok: steps.every((x) => (x.frames?.length ?? 0) > 0),
            label: `Every web step has captured AGY Browser frames (${steps.filter((x) => (x.frames?.length ?? 0) > 0).length}/${steps.length})`,
            fix: <button className="underline" onClick={() => goto("rehearse")}>AGY Browser tab</button>,
          },
        ]
      : []),
  ];
  const blocking = checks.filter((c) => !c.ok && !("soft" in c && c.soft));

  return (
    <div className="space-y-5">
      <div className="card p-5">
        <ul className="mb-4 space-y-2">
          {checks.map((c) => (
            <li key={c.label} className="flex items-center gap-2 text-xs sm:text-sm">
              {c.ok ? (
                <CheckCircle2 className="size-4 shrink-0 text-emerald-600" />
              ) : "soft" in c && c.soft ? (
                <AlertTriangle className="size-4 shrink-0 text-amber-500" />
              ) : (
                <Circle className="size-4 shrink-0 text-zinc-300" />
              )}
              <span className={c.ok ? "" : "text-zinc-500"}>{c.label}</span>
              {!c.ok && "fix" in c && c.fix && (
                <span className="text-xs text-brand-700 dark:text-brand-100">· {c.fix}</span>
              )}
            </li>
          ))}
        </ul>

        {readiness?.warnings && readiness.warnings.length > 0 && (
          <div className="mb-4">
            <Alert tone="amber">{readiness.warnings[0]}</Alert>
          </div>
        )}

        <fieldset className="mb-4 space-y-2">
          <legend className="label">Video resolution</legend>
          <div className="flex flex-wrap gap-3">
            <label
              htmlFor="res-1080p"
              className="flex cursor-pointer items-center gap-2 rounded-lg border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700"
            >
              <input
                type="radio"
                id="res-1080p"
                name="render-resolution"
                value="1080p"
                checked={activeRes === "1080p"}
                onChange={() => changeResolution("1080p")}
              />
              <span>1080p · Full HD (1920×1080)</span>
            </label>
            <label
              htmlFor="res-4k"
              className="flex cursor-pointer items-center gap-2 rounded-lg border border-zinc-300 px-3 py-2 text-sm dark:border-zinc-700"
            >
              <input
                type="radio"
                id="res-4k"
                name="render-resolution"
                value="4k"
                checked={activeRes === "4k"}
                onChange={() => changeResolution("4k")}
              />
              <span>4K · Ultra HD (3840×2160)</span>
            </label>
          </div>
        </fieldset>
        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant="primary"
            icon={<Clapperboard className="size-4" />}
            busy={job.running}
            disabled={blocking.length > 0}
            onClick={() => {
              setErr("");
              job.start(api.render(p.id, false, activeRes)).catch((e) => setErr(e.message));
            }}
          >
            Render {activeRes === "4k" ? "4K" : "1080p"} MP4
          </Button>
          <span className="text-xs text-zinc-500">
            Gemini TTS audio & supersampled title cards are cached, so re-renders after edits finish in seconds.
          </span>
        </div>
        {s && (
          <p className="mt-3 text-xs text-zinc-500">
            Output directory: <code>{s.output_dir}</code>
          </p>
        )}
      </div>

      {err && <Alert>{err}</Alert>}
      <JobStatus job={job.job} />

      {p.renders.map((r, i) => (
        <RenderCard
          key={`${r.file}-${r.created_at}`}
          projectId={p.id}
          projectName={p.name}
          render={r}
          index={i}
          gdrive={gdrive}
          onRefreshGdrive={refreshGdrive}
          onRefreshProject={refresh}
        />
      ))}
    </div>
  );
}

function RenderCard({
  projectId,
  projectName,
  render: r,
  index: i,
  gdrive,
  onRefreshGdrive,
  onRefreshProject,
}: {
  projectId: string;
  projectName: string;
  render: Render;
  index: number;
  gdrive: GDriveStatus | null;
  onRefreshGdrive: () => void;
  onRefreshProject: () => void;
}) {
  const isSidecar = inAntigravitySidecar();
  const [dlBusy, setDlBusy] = useState(false);
  const [downloadedPath, setDownloadedPath] = useState("");
  const [pickerOpen, setPickerOpen] = useState(false);
  const [driveBusy, setDriveBusy] = useState(false);
  const [drivePending, setDrivePending] = useState(false);
  const [setupBusy, setSetupBusy] = useState(false);
  const [setupRequested, setSetupRequested] = useState(false);
  const [refreshingFolders, setRefreshingFolders] = useState(false);
  const [cardErr, setCardErr] = useState("");
  const prevConnected = useRef<boolean>(Boolean(gdrive?.connected));

  useEffect(() => {
    const nowConnected = Boolean(gdrive?.connected);
    if (!prevConnected.current && nowConnected && setupRequested) {
      setSetupRequested(false);
      setPickerOpen(true);
    }
    prevConnected.current = nowConnected;
  }, [gdrive?.connected, setupRequested]);

  useEffect(() => {
    setRefreshingFolders(false);
  }, [gdrive?.updated_at]);

  useEffect(() => {
    if (!drivePending) return;
    const t = window.setInterval(onRefreshProject, 2500);
    return () => window.clearInterval(t);
  }, [drivePending, onRefreshProject]);

  useEffect(() => {
    if (r.drive_url) {
      setDrivePending(false);
      setPickerOpen(false);
    }
  }, [r.drive_url, r.drive_uploaded_at]);

  const filename = r.file.split("/").pop() || `${projectId}-demo.mp4`;
  const driveStatus = gdrive?.status ?? "not_installed";
  const driveConnected = driveStatus === "connected";

  const handleDownload = async () => {
    setCardErr("");
    setDlBusy(true);
    try {
      const out = await api.downloadLocal(projectId, i, { choose_location: true });
      if (!out.canceled && out.saved_to) {
        setDownloadedPath(out.saved_to);
      }
    } catch (e) {
      setCardErr((e as Error).message);
    } finally {
      setDlBusy(false);
    }
  };

  const handleInitiateDriveSetup = async () => {
    setCardErr("");
    setSetupBusy(true);
    try {
      let prompt: string;
      if (driveStatus === "not_installed") {
        prompt =
          `Please install and connect the official Google Drive (gdrive) plugin in Antigravity so I can push rendered videos from Voice Demo Studio. ` +
          `Show the Google Drive plugin card, and once I am signed in, sync my Google Drive folders via sync_gdrive_state (or POST /api/gdrive/state).`;
      } else if (driveStatus === "disabled") {
        prompt =
          `The Google Drive (gdrive) plugin is currently disabled in Antigravity. Please share the customization link so I can enable it, ` +
          `and once enabled and signed in, sync my Google Drive folders via sync_gdrive_state (or POST /api/gdrive/state).`;
      } else {
        prompt =
          `Please verify or initiate my Google Drive (gdrive) sign-in in Antigravity for Voice Demo Studio. ` +
          `If gdrive is not signed in yet, show the Google Drive sign-in card; if I am already signed in, fetch my Drive folders ` +
          `(gdrive readonly search --type folder --max 400 --json) and call sync_gdrive_state (or POST /api/gdrive/state) so Push to Google Drive unlocks.`;
      }
      const sent = await sendToAntigravity(prompt);
      if (!sent) {
        throw new Error("Open Voice Demo Studio inside Google Antigravity to install or sign in to Google Drive.");
      }
      setSetupRequested(true);
      onRefreshGdrive();
    } catch (e) {
      setCardErr((e as Error).message);
    } finally {
      setSetupBusy(false);
    }
  };

  const handleRefreshFolders = async () => {
    setCardErr("");
    setRefreshingFolders(true);
    try {
      const sent = await sendToAntigravity(
        `Refresh my Google Drive folder list for Voice Demo Studio: run \`gdrive readonly search --type folder --max 400 --json\` ` +
          `and persist the updated folder hierarchy via \`sync_gdrive_state\` (or \`POST /api/gdrive/state\`).`,
      );
      if (!sent) {
        setRefreshingFolders(false);
        throw new Error("Open Voice Demo Studio inside Google Antigravity to refresh Google Drive folders.");
      }
    } catch (e) {
      setRefreshingFolders(false);
      setCardErr((e as Error).message);
    }
  };

  const handleConfirmDriveUpload = async (dest: DriveDestination) => {
    setCardErr("");
    setDriveBusy(true);
    try {
      saveDriveFolderId(dest.folderId);
      const targetDesc =
        dest.folderId === "root" && !dest.newSubfolder
          ? `into My Drive root (folder_id="root")`
          : dest.newSubfolder
            ? `by creating new subfolder "${dest.newSubfolder}" inside parent folder_id="${dest.folderId}" (full path: "${dest.folderPath}")`
            : `into Google Drive folder "${dest.folderPath}" (folder_id="${dest.folderId}")`;

      const prompt =
        `Upload rendered MP4 #${i} ("${r.file}") for Voice Demo Lab project "${projectName}" (${projectId}) ${targetDesc} ` +
        `using the official Google Drive (gdrive) plugin. Once uploaded, record the shareable Drive URL, file ID, and drive_folder="${dest.folderPath}" ` +
        `on render index ${i} via record_render_drive_upload (or PATCH /api/projects/${projectId}/renders/${i}).`;

      const sent = await sendToAntigravity(prompt);
      if (!sent) {
        throw new Error("Open Voice Demo Studio inside Google Antigravity to push directly via the Google Drive plugin.");
      }
      setDrivePending(true);
      setPickerOpen(false);
    } catch (e) {
      setCardErr((e as Error).message);
    } finally {
      setDriveBusy(false);
    }
  };

  const setupButtonLabel =
    driveStatus === "not_installed"
      ? "Install Google Drive"
      : driveStatus === "disabled"
        ? "Enable Google Drive"
        : setupRequested
          ? "Verify Google Drive Sign-In"
          : "Sign in to Google Drive";

  return (
    <div className="card overflow-hidden">
      <video src={videoUrl(projectId, i)} controls preload="metadata" className="aspect-video w-full bg-black" />
      <div className="space-y-2.5 px-4 py-3 text-xs">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium">{new Date(r.created_at * 1000).toLocaleString()}</span>
          <Badge tone={r.resolution === "4k" ? "violet" : "blue"}>
            {r.resolution === "4k" ? "4K" : "1080p"} · {r.width || (r.resolution === "4k" ? 3840 : 1920)}×{r.height || (r.resolution === "4k" ? 2160 : 1080)}
          </Badge>
          <span className="text-zinc-500">
            {Math.floor(r.seconds / 60)}:{String(Math.round(r.seconds % 60)).padStart(2, "0")} · {r.segments} segments
          </span>
          {r.drive_url && (
            <Badge tone="green">
              Synced to Drive{r.drive_folder ? ` (${r.drive_folder})` : ""}
            </Badge>
          )}
          <span className="min-w-0 flex-1 truncate text-right font-mono text-[11px] text-zinc-500" title={r.file}>
            {filename}
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2 pt-0.5">
          <Button
            size="sm"
            variant="primary"
            busy={dlBusy}
            icon={<Download className="size-3.5" />}
            onClick={handleDownload}
          >
            Download MP4
          </Button>

          {r.drive_url && (
            <a
              href={r.drive_url}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 py-1.5 text-xs font-medium text-emerald-800 transition hover:bg-emerald-100 dark:border-emerald-800/60 dark:bg-emerald-950/40 dark:text-emerald-200"
            >
              <ExternalLink className="size-3.5" /> Open in Google Drive
            </a>
          )}

          {isSidecar && (
            <>
              <Button
                size="sm"
                variant={r.drive_url ? "ghost" : "secondary"}
                disabled={!driveConnected}
                icon={<CloudUpload className="size-3.5" />}
                onClick={() => setPickerOpen(true)}
                title={
                  driveConnected
                    ? "Choose a Google Drive folder graphically and upload this MP4"
                    : driveStatus === "not_installed"
                      ? "Google Drive plugin is not installed in Antigravity yet"
                      : driveStatus === "disabled"
                        ? "Google Drive plugin is disabled in Antigravity"
                        : "Sign in to Google Drive in Antigravity to enable uploads"
                }
              >
                {r.drive_url ? "Re-push to Google Drive" : "Push to Google Drive"}
              </Button>

              {!driveConnected && (
                <Button
                  size="sm"
                  variant="secondary"
                  busy={setupBusy}
                  icon={
                    driveStatus === "not_installed" || driveStatus === "disabled" ? (
                      <PlugZap className="size-3.5 text-brand-600 dark:text-brand-300" />
                    ) : (
                      <LogIn className="size-3.5 text-brand-600 dark:text-brand-300" />
                    )
                  }
                  onClick={handleInitiateDriveSetup}
                  className="border-brand-300 text-brand-700 hover:bg-brand-50 dark:border-brand-700 dark:text-brand-200 dark:hover:bg-brand-950/40"
                >
                  {setupButtonLabel}
                </Button>
              )}
            </>
          )}

          <Button size="sm" variant="ghost" icon={<FolderOpen className="size-3.5" />} onClick={() => api.reveal(projectId, i)}>
            Show in Finder
          </Button>
        </div>

        {downloadedPath && (
          <Alert tone="blue">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="truncate">
                Saved to <code>{downloadedPath}</code>
              </span>
              <button
                type="button"
                onClick={() => api.reveal(projectId, i, true)}
                className="shrink-0 font-semibold underline"
              >
                Show in Finder
              </button>
            </div>
          </Alert>
        )}

        {setupRequested && !driveConnected && (
          <Alert tone="blue">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span>
                Check the Antigravity chat pane to complete Google Drive{" "}
                {driveStatus === "not_installed" ? "installation & sign-in" : driveStatus === "disabled" ? "enablement" : "sign-in"}.
                Once signed in, click <strong>Verify Google Drive Sign-In</strong> to load your folders and unlock{" "}
                <strong>Push to Google Drive</strong>.
              </span>
            </div>
          </Alert>
        )}

        {drivePending && !r.drive_url && (
          <Alert tone="blue">
            Uploading MP4 to Google Drive via Antigravity — this card will display <strong>Open in Google Drive</strong>{" "}
            automatically once complete.
          </Alert>
        )}

        {cardErr && <Alert>{cardErr}</Alert>}
      </div>

      <DriveFolderModal
        open={pickerOpen && driveConnected}
        accountEmail={gdrive?.account_email || ""}
        folders={gdrive?.folders || []}
        filename={filename}
        busy={driveBusy}
        refreshing={refreshingFolders}
        initialFolderId={loadSavedDriveFolderId()}
        onClose={() => setPickerOpen(false)}
        onRefreshFolders={handleRefreshFolders}
        onConfirm={handleConfirmDriveUpload}
      />
    </div>
  );
}

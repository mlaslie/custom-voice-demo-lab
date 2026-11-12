import { AlertTriangle, CheckCircle2, Circle, Clapperboard, CloudUpload, Download, ExternalLink, FolderOpen } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, inAntigravitySidecar, sendToAntigravity, videoDownloadUrl, videoUrl, type Readiness, type Render, type Settings } from "../../api";
import { JobStatus, useJob } from "../../components/hooks";
import { Alert, Badge, Button } from "../../components/ui";
import type { TabProps } from "../Project";

const DRIVE_FOLDER_KEY = "demolab_drive_folder";

function loadSavedDriveFolder(): string {
  try { return localStorage.getItem(DRIVE_FOLDER_KEY) || ""; } catch { return ""; }
}
function saveDriveFolder(v: string) {
  try { localStorage.setItem(DRIVE_FOLDER_KEY, v); } catch { /* ignore */ }
}

export default function RenderTab({ project: p, refresh, goto }: TabProps) {
  const [s, setS] = useState<Settings | null>(null);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [err, setErr] = useState("");
  const job = useJob(() => {
    refresh();
    api.readiness(p.id).then(setReadiness).catch(() => {});
  });

  useEffect(() => { api.settings().then(setS).catch(() => {}); }, []);
  useEffect(() => { api.readiness(p.id).then(setReadiness).catch(() => {}); }, [p]);
  useEffect(() => {
    api.jobs(p.id).then((js) => {
      const r = js.find((j) => j.kind === "render" && j.state === "running");
      if (r) job.start(Promise.resolve(r));
    });
  }, [p.id]);

  const steps = p.segments.filter((x) => x.type === "step");
  const authOk = p.web_auth?.status === "authenticated" || p.web_auth?.status === "not_needed" || p.has_login;
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
    ...(steps.length ? [
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
    ] : []),
  ];
  const blocking = checks.filter((c) => !c.ok && !("soft" in c && c.soft));

  return (
    <div className="space-y-5">
      <div className="card p-5">
        <ul className="mb-4 space-y-2">
          {checks.map((c) => (
            <li key={c.label} className="flex items-center gap-2 text-xs sm:text-sm">
              {c.ok
                ? <CheckCircle2 className="size-4 shrink-0 text-emerald-600" />
                : "soft" in c && c.soft
                  ? <AlertTriangle className="size-4 shrink-0 text-amber-500" />
                  : <Circle className="size-4 shrink-0 text-zinc-300" />}
              <span className={c.ok ? "" : "text-zinc-500"}>{c.label}</span>
              {!c.ok && "fix" in c && c.fix && <span className="text-xs text-brand-700 dark:text-brand-100">· {c.fix}</span>}
            </li>
          ))}
        </ul>

        {readiness?.warnings && readiness.warnings.length > 0 && (
          <div className="mb-4">
            <Alert tone="amber">{readiness.warnings[0]}</Alert>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant="primary"
            icon={<Clapperboard className="size-4" />}
            busy={job.running}
            disabled={blocking.length > 0}
            onClick={() => { setErr(""); job.start(api.render(p.id)).catch((e) => setErr(e.message)); }}
          >
            Render 1080p MP4
          </Button>
          <span className="text-xs text-zinc-500">
            Gemini TTS audio & 2× supersampled title cards are cached, so re-renders after edits finish in seconds.
          </span>
        </div>
        {s && <p className="mt-3 text-xs text-zinc-500">Output directory: <code>{s.output_dir}</code></p>}
      </div>

      {err && <Alert>{err}</Alert>}
      <JobStatus job={job.job} />

      {p.renders.map((r, i) => (
        <RenderCard key={`${r.file}-${r.created_at}`} projectId={p.id} projectName={p.name} render={r} index={i} />
      ))}
    </div>
  );
}

function RenderCard({
  projectId,
  projectName,
  render: r,
  index: i,
}: {
  projectId: string;
  projectName: string;
  render: Render;
  index: number;
}) {
  const isSidecar = inAntigravitySidecar();
  const [dlBusy, setDlBusy] = useState(false);
  const [downloadedPath, setDownloadedPath] = useState("");
  const [driveOpen, setDriveOpen] = useState(false);
  const [driveFolder, setDriveFolder] = useState(r.drive_folder || loadSavedDriveFolder());
  const [driveBusy, setDriveBusy] = useState(false);
  const [drivePending, setDrivePending] = useState(false);
  const [cardErr, setCardErr] = useState("");

  useEffect(() => {
    if (r.drive_url) {
      setDrivePending(false);
      setDriveOpen(false);
    }
  }, [r.drive_url, r.drive_uploaded_at]);

  const filename = r.file.split("/").pop() || `${projectId}-demo.mp4`;

  const handleDownload = async () => {
    setCardErr("");
    if (!isSidecar) {
      const a = document.createElement("a");
      a.href = videoDownloadUrl(projectId, i);
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      return;
    }
    setDlBusy(true);
    try {
      const out = await api.downloadLocal(projectId, i);
      setDownloadedPath(out.saved_to);
    } catch (e) {
      setCardErr((e as Error).message);
    } finally {
      setDlBusy(false);
    }
  };

  const handlePushToDrive = async () => {
    setCardErr("");
    setDriveBusy(true);
    try {
      const trimmedFolder = driveFolder.trim();
      saveDriveFolder(trimmedFolder);
      const folderClause = trimmedFolder ? ` into Google Drive folder "${trimmedFolder}"` : " into my Google Drive";
      const prompt =
        `Upload rendered MP4 #${i} ("${r.file}") for Voice Demo Lab project "${projectName}" (${projectId})${folderClause} ` +
        `using the official Google Drive (gdrive) plugin. Once uploaded, record the shareable Drive URL and file ID on render index ${i} ` +
        `via record_render_drive_upload (or PATCH /api/projects/${projectId}/renders/${i}).`;
      const sent = await sendToAntigravity(prompt);
      if (!sent) {
        throw new Error("Open Voice Demo Studio inside Google Antigravity to push directly via the Google Drive plugin.");
      }
      setDrivePending(true);
      setDriveOpen(false);
    } catch (e) {
      setCardErr((e as Error).message);
    } finally {
      setDriveBusy(false);
    }
  };

  return (
    <div className="card overflow-hidden">
      <video src={videoUrl(projectId, i)} controls preload="metadata" className="aspect-video w-full bg-black" />
      <div className="space-y-2.5 px-4 py-3 text-xs">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium text-sm">{new Date(r.created_at * 1000).toLocaleString()}</span>
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

          {r.drive_url ? (
            <>
              <a
                href={r.drive_url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-200 bg-emerald-50 px-2.5 py-1.5 text-xs font-medium text-emerald-800 transition hover:bg-emerald-100 dark:border-emerald-800/60 dark:bg-emerald-950/40 dark:text-emerald-200"
              >
                <ExternalLink className="size-3.5" /> Open in Google Drive
              </a>
              {isSidecar && (
                <Button size="sm" variant="ghost" icon={<CloudUpload className="size-3.5" />} onClick={() => setDriveOpen(!driveOpen)}>
                  Re-push
                </Button>
              )}
            </>
          ) : (
            isSidecar && (
              <Button
                size="sm"
                icon={<CloudUpload className="size-3.5" />}
                onClick={() => setDriveOpen(!driveOpen)}
              >
                Push to Google Drive
              </Button>
            )
          )}

          <Button size="sm" variant="ghost" icon={<FolderOpen className="size-3.5" />} onClick={() => api.reveal(projectId, i)}>
            Show in Finder
          </Button>
        </div>

        {driveOpen && (
          <div className="flex flex-wrap items-center gap-2 rounded-xl border border-zinc-200 bg-zinc-50 p-2.5 dark:border-zinc-800 dark:bg-zinc-900/70">
            <input
              className="input !w-auto min-w-44 flex-1 !py-1.5 text-xs"
              value={driveFolder}
              onChange={(e) => setDriveFolder(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") handlePushToDrive(); }}
              placeholder="Drive folder name (optional — empty = My Drive root)"
            />
            <Button size="sm" variant="primary" busy={driveBusy} icon={<CloudUpload className="size-3.5" />} onClick={handlePushToDrive}>
              Upload via AGY
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setDriveOpen(false)}>
              Cancel
            </Button>
          </div>
        )}

        {downloadedPath && (
          <Alert tone="blue">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="truncate">Saved to <code>{downloadedPath}</code></span>
              <button
                onClick={() => api.reveal(projectId, i, true)}
                className="shrink-0 font-semibold underline"
              >
                Reveal in Downloads
              </button>
            </div>
          </Alert>
        )}

        {drivePending && !r.drive_url && (
          <Alert tone="blue">
            Requested Google Drive upload in Antigravity chat — this card will show <strong>Open in Google Drive</strong> automatically once finished.
          </Alert>
        )}

        {cardErr && <Alert>{cardErr}</Alert>}
      </div>
    </div>
  );
}

import {
  Check,
  ChevronRight,
  CloudUpload,
  Folder,
  FolderOpen,
  FolderPlus,
  HardDrive,
  RefreshCw,
  Search,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { GDriveFolder } from "../api";
import { Badge, Button } from "./ui";

export interface DriveDestination {
  folderId: string;
  folderPath: string;
  newSubfolder: string;
}

interface DriveFolderModalProps {
  open: boolean;
  accountEmail: string;
  folders: GDriveFolder[];
  filename: string;
  busy?: boolean;
  refreshing?: boolean;
  initialFolderId?: string;
  onClose: () => void;
  onRefreshFolders: () => void;
  onConfirm: (dest: DriveDestination) => void;
}

export default function DriveFolderModal({
  open,
  accountEmail,
  folders,
  filename,
  busy = false,
  refreshing = false,
  initialFolderId = "root",
  onClose,
  onRefreshFolders,
  onConfirm,
}: DriveFolderModalProps) {
  const byId = useMemo(() => {
    const m = new Map<string, GDriveFolder>();
    for (const f of folders) m.set(f.id, f);
    return m;
  }, [folders]);

  const validInitial = initialFolderId !== "root" && byId.has(initialFolderId) ? initialFolderId : "root";
  const [currentFolderId, setCurrentFolderId] = useState<string>(validInitial);
  const [selectedFolderId, setSelectedFolderId] = useState<string>(validInitial);
  const [query, setQuery] = useState("");
  const [creatingNew, setCreatingNew] = useState(false);
  const [newSubfolder, setNewSubfolder] = useState("");

  useEffect(() => {
    if (!open) return;
    const start = initialFolderId !== "root" && byId.has(initialFolderId) ? initialFolderId : "root";
    setCurrentFolderId(start);
    setSelectedFolderId(start);
    setQuery("");
    setCreatingNew(false);
    setNewSubfolder("");
  }, [open, initialFolderId, byId]);

  const childCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const f of folders) {
      const p = f.parent_id && byId.has(f.parent_id) ? f.parent_id : "root";
      counts.set(p, (counts.get(p) || 0) + 1);
    }
    return counts;
  }, [folders, byId]);

  const buildPathSegments = (folderId: string): { id: string; name: string }[] => {
    const chain: { id: string; name: string }[] = [];
    const visited = new Set<string>();
    let cur = folderId;
    while (cur && cur !== "root" && byId.has(cur) && !visited.has(cur)) {
      visited.add(cur);
      const item = byId.get(cur)!;
      chain.unshift({ id: item.id, name: item.name });
      cur = item.parent_id || "root";
    }
    return [{ id: "root", name: "My Drive" }, ...chain];
  };

  const breadcrumbs = useMemo(() => buildPathSegments(currentFolderId), [currentFolderId, byId]);

  const visibleFolders = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (q) {
      return folders
        .filter((f) => f.name.toLowerCase().includes(q))
        .sort((a, b) => a.name.localeCompare(b.name));
    }
    return folders
      .filter((f) => {
        const normParent = f.parent_id && byId.has(f.parent_id) ? f.parent_id : "root";
        return normParent === currentFolderId;
      })
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [folders, byId, currentFolderId, query]);

  if (!open) return null;

  const selectedSegments = buildPathSegments(selectedFolderId);
  const basePath = selectedSegments.map((s) => s.name).join(" / ");
  const trimmedNew = creatingNew ? newSubfolder.trim() : "";
  const fullDestinationPath = trimmedNew ? `${basePath} / ${trimmedNew}` : basePath;

  const enterFolder = (id: string) => {
    setQuery("");
    setCurrentFolderId(id);
    setSelectedFolderId(id);
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-3 backdrop-blur-[1px]"
      onClick={onClose}
    >
      <div
        className="card flex max-h-[88vh] w-full max-w-lg flex-col overflow-hidden shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-3 border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-sm font-semibold">Choose Google Drive Folder</h3>
              {accountEmail && <Badge tone="green">{accountEmail}</Badge>}
            </div>
            <p className="mt-0.5 truncate text-xs text-zinc-500" title={filename}>
              Uploading <code>{filename}</code>
            </p>
          </div>
          <div className="flex items-center gap-1">
            <Button
              size="sm"
              variant="ghost"
              busy={refreshing}
              icon={<RefreshCw className="size-3.5" />}
              onClick={onRefreshFolders}
              title="Re-sync Google Drive folders via Antigravity"
            >
              Refresh
            </Button>
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg p-1.5 text-zinc-400 hover:bg-zinc-100 hover:text-zinc-700 dark:hover:bg-zinc-800 dark:hover:text-zinc-200"
              aria-label="Close"
            >
              <X className="size-4" />
            </button>
          </div>
        </div>

        {/* Breadcrumbs + Search */}
        <div className="space-y-2 border-b border-zinc-200 bg-zinc-50/70 px-4 py-2.5 dark:border-zinc-800 dark:bg-zinc-900/60">
          <div className="flex flex-wrap items-center gap-1 text-xs">
            {breadcrumbs.map((crumb, idx) => {
              const isLast = idx === breadcrumbs.length - 1;
              return (
                <span key={crumb.id} className="inline-flex items-center gap-1">
                  {idx > 0 && <ChevronRight className="size-3.5 text-zinc-400" />}
                  <button
                    type="button"
                    onClick={() => enterFolder(crumb.id)}
                    className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 transition ${
                      isLast
                        ? "bg-brand-50 font-semibold text-brand-700 dark:bg-brand-700/25 dark:text-brand-100"
                        : "text-zinc-600 hover:bg-zinc-200/70 dark:text-zinc-300 dark:hover:bg-zinc-800"
                    }`}
                  >
                    {crumb.id === "root" && <HardDrive className="size-3" />}
                    {crumb.name}
                  </button>
                </span>
              );
            })}
          </div>

          <div className="flex items-center gap-2">
            <div className="relative flex-1">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-zinc-400" />
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Filter folders across My Drive…"
                className="input !py-1.5 !pl-8 text-xs"
              />
            </div>
            <Button
              size="sm"
              variant={creatingNew ? "primary" : "secondary"}
              icon={<FolderPlus className="size-3.5" />}
              onClick={() => setCreatingNew((v) => !v)}
            >
              New Folder
            </Button>
          </div>

          {creatingNew && (
            <div className="flex items-center gap-2 rounded-lg border border-brand-200 bg-brand-50/60 p-2 dark:border-brand-700/50 dark:bg-brand-950/30">
              <FolderPlus className="size-4 shrink-0 text-brand-600 dark:text-brand-300" />
              <input
                type="text"
                autoFocus
                value={newSubfolder}
                onChange={(e) => setNewSubfolder(e.target.value)}
                placeholder={`New subfolder inside ${selectedSegments[selectedSegments.length - 1]?.name || "My Drive"}…`}
                className="input !py-1 text-xs"
              />
            </div>
          )}
        </div>

        {/* Graphical Folder List */}
        <div className="min-h-[220px] max-h-[320px] flex-1 overflow-y-auto p-2">
          {/* Current folder selectable row */}
          {!query.trim() && (
            <button
              type="button"
              onClick={() => setSelectedFolderId(currentFolderId)}
              className={`mb-1 flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-xs transition ${
                selectedFolderId === currentFolderId
                  ? "bg-brand-50 text-brand-800 ring-1 ring-brand-300 dark:bg-brand-700/25 dark:text-brand-100 dark:ring-brand-600"
                  : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-300 dark:hover:bg-zinc-800/70"
              }`}
            >
              <span className="flex items-center gap-2 font-medium">
                <FolderOpen className="size-4 shrink-0 text-brand-600 dark:text-brand-300" />
                Save directly in “{breadcrumbs[breadcrumbs.length - 1]?.name || "My Drive"}”
              </span>
              {selectedFolderId === currentFolderId && <Check className="size-4 shrink-0 text-brand-600 dark:text-brand-200" />}
            </button>
          )}

          {visibleFolders.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-1.5 py-10 text-center text-xs text-zinc-500">
              <Folder className="size-7 text-zinc-300 dark:text-zinc-600" />
              {query.trim() ? (
                <p>No folders match “{query.trim()}”.</p>
              ) : folders.length === 0 ? (
                <>
                  <p>No subfolders loaded yet (uploading directly to My Drive works right away).</p>
                  <button type="button" onClick={onRefreshFolders} className="font-medium text-brand-600 underline dark:text-brand-300">
                    Load subfolders from Google Drive
                  </button>
                </>
              ) : (
                <p>No subfolders inside this folder.</p>
              )}
            </div>
          ) : (
            <ul className="space-y-0.5">
              {visibleFolders.map((folder) => {
                const isSelected = selectedFolderId === folder.id;
                const subCount = childCounts.get(folder.id) || 0;
                const parentPath = query.trim()
                  ? buildPathSegments(folder.parent_id || "root").map((s) => s.name).join(" / ")
                  : "";
                return (
                  <li
                    key={folder.id}
                    onClick={() => setSelectedFolderId(folder.id)}
                    onDoubleClick={() => enterFolder(folder.id)}
                    className={`group flex cursor-pointer items-center justify-between gap-2 rounded-lg px-3 py-2 text-xs transition ${
                      isSelected
                        ? "bg-brand-50 text-brand-900 ring-1 ring-brand-300 dark:bg-brand-700/25 dark:text-brand-100 dark:ring-brand-600"
                        : "hover:bg-zinc-100 dark:hover:bg-zinc-800/70"
                    }`}
                  >
                    <div className="flex min-w-0 items-center gap-2.5">
                      <Folder
                        className={`size-4 shrink-0 ${
                          isSelected ? "fill-brand-500/20 text-brand-600 dark:text-brand-300" : "text-amber-500"
                        }`}
                      />
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span className="truncate font-medium">{folder.name}</span>
                          {folder.shared && <Badge tone="zinc">Shared</Badge>}
                        </div>
                        {parentPath && (
                          <div className="truncate text-[11px] text-zinc-400">{parentPath}</div>
                        )}
                      </div>
                    </div>

                    <div className="flex shrink-0 items-center gap-1.5">
                      {subCount > 0 && (
                        <span className="text-[11px] text-zinc-400">{subCount}</span>
                      )}
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          enterFolder(folder.id);
                        }}
                        className="inline-flex items-center gap-0.5 rounded-md px-2 py-1 text-[11px] font-medium text-zinc-500 hover:bg-zinc-200/80 hover:text-zinc-900 dark:text-zinc-400 dark:hover:bg-zinc-700 dark:hover:text-zinc-100"
                        title={`Open ${folder.name}`}
                      >
                        Open <ChevronRight className="size-3.5" />
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* Footer */}
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-zinc-200 bg-zinc-50/70 px-4 py-3 text-xs dark:border-zinc-800 dark:bg-zinc-900/60">
          <div className="min-w-0 flex-1">
            <span className="text-zinc-500">Destination: </span>
            <span className="font-semibold text-zinc-800 dark:text-zinc-100" title={fullDestinationPath}>
              {fullDestinationPath}
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button
              size="sm"
              variant="primary"
              busy={busy}
              icon={<CloudUpload className="size-3.5" />}
              onClick={() =>
                onConfirm({
                  folderId: selectedFolderId,
                  folderPath: fullDestinationPath,
                  newSubfolder: trimmedNew,
                })
              }
            >
              Upload MP4 Here
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

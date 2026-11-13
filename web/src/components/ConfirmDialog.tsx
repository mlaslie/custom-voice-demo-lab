import { useEffect, useId, useRef, useState } from "react";
import { Button } from "./ui";

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  body: string;
  confirmLabel?: string;
  cancelLabel?: string;
  checkboxLabel?: string;
  defaultChecked?: boolean;
  danger?: boolean;
  busy?: boolean;
  onCancel: () => void;
  onConfirm: (checked: boolean) => void;
}

export function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel = "Delete",
  cancelLabel = "Cancel",
  checkboxLabel,
  defaultChecked = false,
  danger = true,
  busy = false,
  onCancel,
  onConfirm,
}: ConfirmDialogProps) {
  const titleId = useId();
  const dlgRef = useRef<HTMLDialogElement | null>(null);
  const [checked, setChecked] = useState(defaultChecked);
  const downOutsideRef = useRef(false);

  useEffect(() => {
    setChecked(defaultChecked);
  }, [open, defaultChecked]);

  useEffect(() => {
    const dlg = dlgRef.current;
    if (!dlg) return;
    if (open) {
      if (!dlg.open) dlg.showModal();
    } else if (dlg.open) {
      dlg.close();
    }
  }, [open]);

  const isOutside = (e: React.PointerEvent<HTMLDialogElement>, dlg: HTMLDialogElement) => {
    const r = dlg.getBoundingClientRect();
    return e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
  };

  return (
    <dialog
      ref={dlgRef}
      aria-labelledby={titleId}
      {...({ closedby: "any" } as Record<string, string>)}
      onCancel={(e) => {
        e.preventDefault();
        if (!busy) onCancel();
      }}
      onPointerDown={(e) => {
        const dlg = dlgRef.current;
        downOutsideRef.current = Boolean(dlg && isOutside(e, dlg));
      }}
      onPointerUp={(e) => {
        const dlg = dlgRef.current;
        if (!busy && downOutsideRef.current && dlg && isOutside(e, dlg)) {
          onCancel();
        }
        downOutsideRef.current = false;
      }}
      className="w-[calc(100%-2rem)] max-w-md rounded-2xl border border-zinc-200 bg-white p-0 text-zinc-900 shadow-xl dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-100"
    >
      <div className="space-y-4 p-5">
        <div className="space-y-1.5">
          <h2 id={titleId} className="text-base font-semibold tracking-tight">
            {title}
          </h2>
          <p className="text-xs leading-relaxed text-zinc-600 dark:text-zinc-400">{body}</p>
        </div>

        {checkboxLabel && (
          <label className="flex cursor-pointer items-start gap-2.5 rounded-xl border border-zinc-200 bg-zinc-50 p-3 text-xs dark:border-zinc-800 dark:bg-zinc-950">
            <input
              type="checkbox"
              className="mt-0.5 size-4 shrink-0"
              checked={checked}
              onChange={(e) => setChecked(e.target.checked)}
              disabled={busy}
            />
            <span className="leading-snug text-zinc-700 dark:text-zinc-300">{checkboxLabel}</span>
          </label>
        )}

        <div className="flex justify-end gap-2">
          <Button size="sm" variant="secondary" disabled={busy} onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button
            size="sm"
            variant={danger ? "danger" : "primary"}
            busy={busy}
            className={danger ? "bg-red-600 text-white hover:bg-red-700 dark:hover:bg-red-700" : ""}
            onClick={() => onConfirm(checked)}
          >
            {confirmLabel}
          </Button>
        </div>
      </div>
    </dialog>
  );
}

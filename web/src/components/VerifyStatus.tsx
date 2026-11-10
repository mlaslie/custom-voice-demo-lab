import { AlertTriangle, CheckCircle2, Loader2, RefreshCw } from "lucide-react";
import { useState } from "react";
import { api, type Settings, type VoiceProfile } from "../api";

/** Whether a saved key + voice pair passed its spoken test, with a button to run it again. */
export function VerifyStatus({ profile: v, onChange, compact = false }:
  { profile: VoiceProfile; onChange: (s: Settings) => void; compact?: boolean }) {
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    try { onChange((await api.verifyProfile(v.id)).settings); } finally { setBusy(false); }
  };
  const when = v.verified_at ? new Date(v.verified_at * 1000).toLocaleString() : "";

  if (busy) return <span className="inline-flex items-center gap-1 text-xs text-zinc-500"><Loader2 className="size-3.5 animate-spin" />Testing…</span>;
  if (v.verified_at) {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-emerald-700 dark:text-emerald-400" title={`Spoke a test phrase on ${when}`}>
        <CheckCircle2 className="size-4" />Verified
        {!compact && <button onClick={run} className="text-zinc-400 hover:text-brand-600" title="Test again"><RefreshCw className="size-3.5" /></button>}
      </span>
    );
  }
  return (
    <span className="inline-flex min-w-0 items-center gap-1.5 text-xs font-medium text-amber-700 dark:text-amber-400" title={v.verify_error || "Not tested yet"}>
      <AlertTriangle className="size-4 shrink-0" />
      <span className="truncate">{v.verify_error ? "Test failed" : "Not verified"}</span>
      {!compact && <button onClick={run} className="shrink-0 rounded-md px-1.5 py-0.5 text-brand-700 hover:bg-brand-50 dark:text-brand-100 dark:hover:bg-brand-700/25">Verify</button>}
    </span>
  );
}

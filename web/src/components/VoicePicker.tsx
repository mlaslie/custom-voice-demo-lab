import { Check, Search, Sparkles, UserRound } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, localeName, type KeyVoices, type Voice } from "../api";
import { VoiceButton } from "./hooks";
import { Alert } from "./ui";

export const SAMPLE = "Hi! This is how I'll sound narrating your demo, from the first slide to the recap.";

/** Choose one of the voices a saved key can use: its project's custom voices, or a standard voice. */
export function VoicePicker({ keyId, value, onPick }: { keyId: string; value: string; onPick: (v: Voice) => void }) {
  const [tab, setTab] = useState<"custom" | "standard">("custom");
  const [locale, setLocale] = useState("");
  const [q, setQ] = useState("");
  const [data, setData] = useState<KeyVoices | null>(null);
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let live = true;
    setLoading(true); setErr("");
    const t = setTimeout(() => api.keyVoices(keyId, locale, q)
      .then((d) => { if (!live) return; setData(d); if (!d.custom.length) setTab((x) => (x === "custom" ? "standard" : x)); })
      .catch((e) => live && setErr((e as Error).message))
      .finally(() => live && setLoading(false)), q ? 250 : 0);
    return () => { live = false; clearTimeout(t); };
  }, [keyId, locale, q]);

  const locales = useMemo(() => (data?.locales ?? [])
    .map((l) => ({ ...l, label: localeName(l.code) }))
    .sort((a, b) => a.label.localeCompare(b.label)), [data?.locales]);

  const list = tab === "custom" ? data?.custom ?? [] : data?.standard ?? [];
  const tabBtn = (k: typeof tab, label: string, n?: number) => (
    <button type="button" onClick={() => setTab(k)}
      className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition ${
        tab === k ? "bg-brand-50 text-brand-700 dark:bg-brand-700/25 dark:text-brand-100" : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"}`}>
      {k === "custom" ? <UserRound className="size-4" /> : <Sparkles className="size-4" />}{label}
      {n !== undefined && <span className="text-xs text-zinc-400">{n}</span>}
    </button>
  );

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-1">
        {tabBtn("custom", "Your custom voices", data?.custom.length)}
        {tabBtn("standard", "Standard voices")}
      </div>
      {tab === "standard" && (
        <div className="flex flex-col gap-2 sm:flex-row">
          <select className="input sm:w-64" value={locale} onChange={(e) => setLocale(e.target.value)} aria-label="Language">
            <option value="">Multilingual ({data?.multilingual ?? 30})</option>
            {locales.map((l) => <option key={l.code} value={l.code}>{l.label} ({l.count})</option>)}
          </select>
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute top-2.5 left-3 size-4 text-zinc-400" />
            <input className="input pl-9" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search: podcaster, storyteller, Kore…" />
          </div>
        </div>
      )}
      {err && <Alert>{err}</Alert>}
      {tab === "custom" && data && !data.custom.length && (
        <Alert tone="blue">This key's AI Studio project has no custom voices. Create one in AI Studio, or pick a standard voice.</Alert>
      )}
      <div className={`max-h-80 divide-y divide-zinc-100 overflow-auto rounded-xl border border-zinc-200 dark:divide-zinc-800 dark:border-zinc-800 ${loading ? "opacity-60" : ""}`}>
        {list.map((v) => {
          const on = v.id === value;
          return (
            <div key={v.id} className={`flex items-center gap-3 px-3 py-2 ${on ? "bg-brand-50/70 dark:bg-brand-700/15" : ""}`}>
              <button type="button" onClick={() => onPick(v)} className="flex min-w-0 flex-1 items-center gap-3 text-left">
                <span className={`grid size-5 shrink-0 place-items-center rounded-full border ${on ? "border-brand-600 bg-brand-600 text-white" : "border-zinc-300 dark:border-zinc-600"}`}>
                  {on && <Check className="size-3" />}
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-sm font-medium">{v.name}</span>
                  <span className="block truncate font-mono text-[11px] text-zinc-500">{v.id}{v.locale ? ` · ${localeName(v.locale)}` : ""}</span>
                </span>
              </button>
              <VoiceButton text={SAMPLE} with={{ key_id: keyId, voice: v.id }} label="Sample" />
            </div>
          );
        })}
        {!list.length && !loading && tab === "standard" && <div className="px-3 py-6 text-center text-sm text-zinc-500">No voices match.</div>}
      </div>
      {tab === "standard" && data && data.standard_total > data.standard.length && (
        <p className="text-xs text-zinc-500">Showing {data.standard.length} of {data.standard_total}. Search to narrow it down.</p>
      )}
    </div>
  );
}

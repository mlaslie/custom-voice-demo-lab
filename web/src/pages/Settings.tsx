import { KeyRound, Lock, Mic, Plus, Save, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Settings } from "../api";
import { VoiceButton } from "../components/hooks";
import { SAMPLE } from "../components/VoicePicker";
import { Alert, Badge, Button, Field } from "../components/ui";

export default function SettingsPage({ onChange }: { onChange: (s: Settings) => void }) {
  const [s, setS] = useState<Settings | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [msg, setMsg] = useState<{ tone: "red" | "blue"; text: string } | null>(null);
  const [busy, setBusy] = useState("");
  const [adding, setAdding] = useState(false);
  const [keyName, setKeyName] = useState("");
  const [secret, setSecret] = useState("");

  const update = (n: Settings) => { setS(n); onChange(n); };
  useEffect(() => { api.settings().then(update); }, []);
  useEffect(() => {
    if (s && !s.setup_needed) api.models().then((m) => setModels(m.filter((x) => x.methods.includes("generateContent")).map((x) => x.name))).catch(() => {});
  }, [s?.setup_needed]);   // eslint-disable-line react-hooks/exhaustive-deps

  if (!s) return null;
  const set = (k: keyof Settings) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setS({ ...s, [k]: e.target.value });
  const keyName_ = (id: string) => { const k = s.keys.find((x) => x.id === id); return k ? `${k.name} (…${k.hint})` : "missing key"; };

  const run = async (name: string, fn: () => Promise<void>) => {
    setBusy(name); setMsg(null);
    try { await fn(); } catch (e) { setMsg({ tone: "red", text: (e as Error).message }); } finally { setBusy(""); }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="mt-1 text-sm text-zinc-500">Stored on this machine and used by every session, in Claude, Antigravity or the browser.</p>
      </div>
      {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}

      <section className="card space-y-4 p-5">
        <div className="flex items-center justify-between gap-3">
          <h2 className="flex items-center gap-2 font-semibold"><Mic className="size-4 text-brand-600" />Voices</h2>
          <Link to={s.keys.length === 1 ? `/setup?use=${s.keys[0].id}` : "/setup"}><Button size="sm" icon={<Plus className="size-4" />}>Add a voice</Button></Link>
        </div>
        <p className="text-sm text-zinc-500">Each voice pairs a saved key with one of its custom voices or a standard voice, with a label and a description your agent can choose by. The active one narrates every project that has not picked its own.</p>
        {!s.profiles.length && <Alert tone="blue">No voices yet. <Link className="font-medium underline" to="/setup">Set one up</Link>.</Alert>}
        <div className="divide-y divide-zinc-100 rounded-xl border border-zinc-200 dark:divide-zinc-800 dark:border-zinc-800">
          {s.profiles.map((v) => {
            const on = v.id === s.active_profile;
            return (
              <div key={v.id} className={`grid gap-3 p-3 sm:grid-cols-[auto_1fr_auto] sm:items-start ${on ? "bg-brand-50/60 dark:bg-brand-700/10" : ""}`}>
                <input type="radio" name="active" className="mt-2.5 size-4 accent-brand-600" checked={on} title="Make this the active voice"
                  onChange={() => run("act", async () => update(await api.activateProfile(v.id)))} />
                <div className="min-w-0 space-y-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <input className="min-w-0 flex-1 bg-transparent font-medium outline-none focus:underline decoration-brand-500/40" defaultValue={v.name}
                      onBlur={(e) => e.target.value.trim() && e.target.value !== v.name && run("p", async () => update(await api.patchProfile(v.id, { name: e.target.value.trim() })))} />
                    {on && <Badge tone="blue">active</Badge>}
                    <Badge tone={v.kind === "custom" ? "violet" : "zinc"}>{v.kind}</Badge>
                  </div>
                  <input className="w-full bg-transparent text-sm text-zinc-600 outline-none placeholder:text-zinc-400 focus:underline decoration-brand-500/40 dark:text-zinc-300" defaultValue={v.description} placeholder="Add a description: when to use this voice"
                    onBlur={(e) => e.target.value !== v.description && run("p", async () => update(await api.patchProfile(v.id, { description: e.target.value.trim() })))} />
                  <div className="truncate text-xs text-zinc-500">{v.voice_name || v.voice} · <span className="font-mono">{v.voice}</span> · key: {keyName_(v.key_id)}</div>
                  <input className="input text-xs" defaultValue={v.style} placeholder="Delivery style"
                    onBlur={(e) => e.target.value !== v.style && run("p", async () => update(await api.patchProfile(v.id, { style: e.target.value })))} />
                </div>
                <div className="flex items-center gap-1 sm:pt-1">
                  <VoiceButton text={SAMPLE} with={{ profile_id: v.id }} label="Sample" />
                  <Button size="sm" variant="danger" title="Delete this voice"
                    onClick={() => confirm(`Delete the voice "${v.name}"?`) && run("del", async () => update(await api.deleteProfile(v.id)))}><Trash2 className="size-4" /></Button>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      <section className="card space-y-4 p-5">
        <div className="flex items-center justify-between gap-3">
          <h2 className="flex items-center gap-2 font-semibold"><KeyRound className="size-4 text-brand-600" />Gemini API keys</h2>
          {!adding && <Button size="sm" icon={<Plus className="size-4" />} onClick={() => setAdding(true)}>Add a key</Button>}
        </div>
        {s.key_source === "env" && <Alert tone="blue">$GEMINI_API_KEY is set in the environment and is used instead of the saved keys.</Alert>}
        <p className="flex items-start gap-2 text-xs text-zinc-500"><Lock className="mt-0.5 size-3.5 shrink-0" />
          Keys are kept in your system keychain. Only a name and the last four characters are shown, and they never pass through the chat or the AI assistant.</p>
        {adding && (
          <div className="grid gap-3 rounded-xl bg-zinc-50 p-3 sm:grid-cols-[1fr_2fr_auto] sm:items-end dark:bg-zinc-950">
            <Field label="Name"><input className="input" value={keyName} onChange={(e) => setKeyName(e.target.value)} placeholder="Work project" /></Field>
            <Field label="API key"><input className="input font-mono" type="password" autoComplete="off" spellCheck={false} value={secret} onChange={(e) => setSecret(e.target.value)} placeholder="AIza…" /></Field>
            <div className="flex gap-2">
              <Button variant="ghost" onClick={() => { setAdding(false); setSecret(""); }}>Cancel</Button>
              <Button variant="primary" busy={busy === "key"} disabled={!secret.trim()}
                onClick={() => run("key", async () => {
                  const r = await api.addKey(keyName || "Gemini key", secret.trim());
                  update(r.settings); setSecret(""); setKeyName(""); setAdding(false);
                  setMsg({ tone: "blue", text: `Key saved. Its project has ${r.custom_voices} custom voice${r.custom_voices === 1 ? "" : "s"}; add a voice to use it.` });
                })}>Check and save</Button>
            </div>
          </div>
        )}
        <div className="divide-y divide-zinc-100 rounded-xl border border-zinc-200 dark:divide-zinc-800 dark:border-zinc-800">
          {s.keys.map((k) => {
            const used = s.profiles.filter((v) => v.key_id === k.id).length;
            return (
              <div key={k.id} className="flex items-center gap-3 px-3 py-2.5">
                <KeyRound className="size-4 shrink-0 text-zinc-400" />
                <div className="min-w-0 flex-1">
                  <div className="truncate text-sm font-medium">{k.name}</div>
                  <div className="font-mono text-xs text-zinc-500">••••••••{k.hint} · used by {used} voice{used === 1 ? "" : "s"}</div>
                </div>
                <Link to={`/setup?use=${k.id}`}><Button size="sm" variant="ghost">Add voice</Button></Link>
                <Button size="sm" variant="danger" disabled={used > 0} title={used ? "Delete the voices that use it first" : "Delete this key"}
                  onClick={() => confirm(`Delete the key "${k.name}" from the keychain?`) && run("delk", async () => update(await api.deleteKey(k.id)))}><Trash2 className="size-4" /></Button>
              </div>
            );
          })}
          {!s.keys.length && <div className="px-3 py-4 text-sm text-zinc-500">No keys saved.</div>}
        </div>
      </section>

      <section className="card space-y-4 p-5">
        <h2 className="font-semibold">Voice model and audience</h2>
        <Field label="Text-to-speech model" hint="Your coding agent writes the scripts; this Gemini model only speaks them."><input className="input font-mono" value={s.tts_model} onChange={set("tts_model")} list="models" /></Field>
        <datalist id="models">{models.map((m) => <option key={m} value={m} />)}</datalist>
        <Field label="Default audience" hint="Shapes how much the script explains."><textarea className="input min-h-16" value={s.audience} onChange={set("audience")} /></Field>
      </section>

      <section className="card space-y-4 p-5">
        <h2 className="font-semibold">Output</h2>
        <Field label="Render folder" hint="Videos and the temporary frame cache go here. Point it at an external drive for long demos.">
          <input className="input font-mono" value={s.output_dir} onChange={set("output_dir")} />
        </Field>
      </section>

      <div className="sticky bottom-4 flex justify-end">
        <Button variant="primary" icon={<Save className="size-4" />} busy={busy === "save"}
          onClick={() => run("save", async () => { update(await api.saveSettings(s)); setMsg({ tone: "blue", text: "Settings saved." }); })}>
          Save settings
        </Button>
      </div>
    </div>
  );
}

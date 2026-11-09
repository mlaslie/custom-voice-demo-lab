import { CheckCircle2, KeyRound, LogIn, LogOut, Mic, Save } from "lucide-react";
import { useEffect, useState } from "react";
import { api, type Settings } from "../api";
import { VoiceButton } from "../components/hooks";
import { Alert, Badge, Button, Field } from "../components/ui";

export default function SettingsPage({ onChange }: { onChange: (s: Settings) => void }) {
  const [s, setS] = useState<Settings | null>(null);
  const [key, setKey] = useState("");
  const [models, setModels] = useState<string[]>([]);
  const [msg, setMsg] = useState<{ tone: "red" | "blue"; text: string } | null>(null);
  const [busy, setBusy] = useState("");
  const [google, setGoogle] = useState<{ state: string; error: string; connected: boolean } | null>(null);
  const [sample, setSample] = useState("Hi! In this demo I'll show you how the gateway keeps every agent's traffic under one set of rules.");

  const update = (n: Settings) => { setS(n); onChange(n); };
  useEffect(() => { api.settings().then(update); api.googleStatus().then(setGoogle).catch(() => {}); }, []);
  useEffect(() => {
    if (s?.gemini_key_set) api.models().then((m) => setModels(m.filter((x) => x.methods.includes("generateContent")).map((x) => x.name))).catch(() => {});
  }, [s?.gemini_key_set]);
  useEffect(() => {
    if (google?.state !== "waiting") return;
    const t = setTimeout(() => api.googleStatus().then((g) => { setGoogle(g); if (g.connected) api.settings().then(update); }), 1500);
    return () => clearTimeout(t);
  }, [google]);

  if (!s) return null;
  const set = (k: keyof Settings) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setS({ ...s, [k]: e.target.value });

  const run = async (name: string, fn: () => Promise<void>) => {
    setBusy(name); setMsg(null);
    try { await fn(); } catch (e) { setMsg({ tone: "red", text: (e as Error).message }); } finally { setBusy(""); }
  };

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="mt-1 text-sm text-zinc-500">Stored on this machine. The API key goes to the OS keychain and is never shown again or sent to the browser.</p>
      </div>
      {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}

      <section className="card space-y-4 p-5">
        <h2 className="flex items-center gap-2 font-semibold"><Mic className="size-4 text-brand-600" />Voice</h2>
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="Custom voice id" hint="From aistudio.google.com, e.g. voice_ab12cd34ef."><input className="input font-mono" value={s.voice_id} onChange={set("voice_id")} placeholder="voice_…" /></Field>
          <Field label="TTS model"><input className="input font-mono" value={s.tts_model} onChange={set("tts_model")} list="models" /></Field>
          <Field label="Delivery style" className="md:col-span-2" hint="How the narrator should sound. Projects can override it."><input className="input" value={s.voice_style} onChange={set("voice_style")} /></Field>
        </div>
        <div className="rounded-xl bg-zinc-50 p-3 dark:bg-zinc-950">
          <span className="label">Try it</span>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
            <input className="input" value={sample} onChange={(e) => setSample(e.target.value)} />
            <VoiceButton text={sample} label="Speak" />
          </div>
          <p className="mt-1 text-xs text-zinc-500">Save first: previews use the saved voice settings.</p>
        </div>
      </section>

      <section className="card space-y-4 p-5">
        <h2 className="flex items-center gap-2 font-semibold"><KeyRound className="size-4 text-brand-600" />Gemini API key
          {s.gemini_key_set ? <Badge tone="green"><CheckCircle2 className="size-3" />set ({s.gemini_key_source})</Badge> : <Badge tone="amber">not set</Badge>}
        </h2>
        <Alert tone="blue">Custom voices belong to the AI Studio project that created them. Use a key from that same project, or the voice returns 404.</Alert>
        {s.gemini_key_source === "env" ? (
          <p className="text-sm text-zinc-500">Using <code>$GEMINI_API_KEY</code> from the environment.</p>
        ) : (
          <div className="flex flex-col gap-2 sm:flex-row">
            <input className="input font-mono" type="password" autoComplete="off" value={key} onChange={(e) => setKey(e.target.value)} placeholder={s.gemini_key_set ? "Replace the saved key…" : "Paste your key"} />
            <Button variant="primary" busy={busy === "key"} disabled={!key} onClick={() => run("key", async () => { update(await api.setKey(key)); setKey(""); setMsg({ tone: "blue", text: "Key saved to the keychain." }); })}>Save key</Button>
            {s.gemini_key_set && <Button variant="danger" onClick={() => run("key", async () => update(await api.clearKey()))}>Remove</Button>}
          </div>
        )}
        <Field label="Script-writing model" hint="Any Gemini text model your key can use.">
          <input className="input font-mono" value={s.script_model} onChange={set("script_model")} list="models" />
        </Field>
        <datalist id="models">{models.map((m) => <option key={m} value={m} />)}</datalist>
        <Field label="Default audience" hint="Shapes how much the script explains."><textarea className="input min-h-16" value={s.audience} onChange={set("audience")} /></Field>
      </section>

      <section className="card space-y-4 p-5">
        <h2 className="flex items-center gap-2 font-semibold">Google Slides
          {s.google_connected ? <Badge tone="green">connected</Badge> : <Badge>not connected</Badge>}
        </h2>
        <Field label="OAuth client secret file" hint={<>A "Desktop app" OAuth client with the Slides and Drive APIs enabled. See docs/google-oauth.md.</>}>
          <input className="input font-mono" value={s.google_client_secret} onChange={set("google_client_secret")} placeholder="~/.demolab/client_secret.json" />
        </Field>
        <div className="flex flex-wrap items-center gap-2">
          {s.google_connected ? (
            <Button icon={<LogOut className="size-4" />} onClick={() => run("g", async () => { await api.googleDisconnect(); update(await api.settings()); })}>Disconnect</Button>
          ) : (
            <Button icon={<LogIn className="size-4" />} busy={google?.state === "waiting"} disabled={!s.google_client_secret}
              onClick={() => run("g", async () => { await api.saveSettings(s); await api.googleConnect(); setGoogle({ state: "waiting", error: "", connected: false }); })}>
              Connect Google
            </Button>
          )}
          {google?.state === "waiting" && <span className="text-sm text-zinc-500">Finish signing in in the browser tab that opened…</span>}
          {google?.state === "error" && <span className="text-sm text-red-600">{google.error}</span>}
        </div>
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

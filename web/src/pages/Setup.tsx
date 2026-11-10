import { AlertTriangle, ArrowRight, CheckCircle2, KeyRound, Lock, Mic, Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, type Settings, type Voice } from "../api";
import { VoicePicker } from "../components/VoicePicker";
import { VerifyStatus } from "../components/VerifyStatus";
import { PacingControl } from "../components/PacingControl";
import { Alert, Button, Field } from "../components/ui";

const DEFAULT_STYLE = "clear, warm, confident product-demo narrator; unhurried pace";

/** First run (and "add a voice" later): save a Gemini API key, pick a voice, save it as a voice profile. */
export default function Setup({ settings, onChange }: { settings: Settings | null; onChange: (s: Settings) => void }) {
  const [params] = useSearchParams();
  const [keyId, setKeyId] = useState(params.get("use") ?? "");
  const [newKey, setNewKey] = useState(!settings?.keys.length);
  const [keyName, setKeyName] = useState("");
  const [secret, setSecret] = useState("");
  const [voice, setVoice] = useState<Voice | null>(null);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [style, setStyle] = useState(DEFAULT_STYLE);
  const [speed, setSpeed] = useState(1);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [done, setDone] = useState<"" | "first" | "more">("");
  const [savedId, setSavedId] = useState("");

  useEffect(() => {
    if (!settings) return;
    if (!keyId && settings.keys.length === 1) setKeyId(settings.keys[0].id);
    setNewKey(!settings.keys.length);
  }, [settings?.keys.length]);   // eslint-disable-line react-hooks/exhaustive-deps

  if (!settings) return null;
  const first = !settings.profiles.length;

  const run = async (n: string, fn: () => Promise<void>) => {
    setBusy(n); setErr("");
    try { await fn(); } catch (e) { setErr((e as Error).message); } finally { setBusy(""); }
  };
  const saveKey = () => run("key", async () => {
    const r = await api.addKey(keyName || "My Gemini key", secret.trim());
    setSecret(""); setKeyName(""); setNewKey(false); setKeyId(r.key.id); onChange(r.settings);
  });
  const saveProfile = () => run("profile", async () => {
    if (!voice) return;
    const wasFirst = !settings?.profiles.length;
    const before = new Set(settings?.profiles.map((v) => v.id));
    const next = await api.addProfile({ name: name.trim() || voice.name, description: description.trim(), key_id: keyId, voice: voice.id,
      voice_name: voice.name, kind: voice.kind, style, speed, activate: true });
    onChange(next);
    setSavedId(next.profiles.find((v) => !before.has(v.id))?.id ?? "");
    setDone(wasFirst ? "first" : "more");
  });

  const saved = settings.profiles.find((v) => v.id === savedId);
  if (done && saved && !saved.verified_at) {
    return (
      <div className="mx-auto max-w-xl">
        <div className="card flex flex-col items-center gap-3 px-6 py-12 text-center">
          <AlertTriangle className="size-10 text-amber-500" />
          <h1 className="text-xl font-semibold">Saved, but the voice test failed</h1>
          <p className="text-sm text-zinc-500">The key and voice were saved, but a test phrase could not be spoken:</p>
          <p className="w-full rounded-lg bg-amber-50 px-3 py-2 text-left text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">{saved.verify_error}</p>
          <div className="mt-2 flex items-center gap-3">
            <VerifyStatus profile={saved} onChange={onChange} />
            <Link to="/settings"><Button>Fix in Settings</Button></Link>
          </div>
        </div>
      </div>
    );
  }
  if (done) {
    return (
      <div className="mx-auto max-w-xl">
        <div className="card flex flex-col items-center gap-3 px-6 py-12 text-center">
          <CheckCircle2 className="size-10 text-emerald-500" />
          <h1 className="text-xl font-semibold">{done === "first" ? "You're all set" : "Voice saved"}</h1>
          {saved && <p className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-3 py-1 text-sm font-medium text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
            <CheckCircle2 className="size-4" />Verified: the key works and the voice spoke a test phrase</p>}
          <p className="text-sm text-zinc-500">
            <b>{name.trim() || voice?.name}</b> is now the active voice, for this session and future ones.
            Go back to your chat to carry on: the assistant will pick it up. You can add more voices or switch between them in Settings.
          </p>
          <div className="mt-2 flex gap-2">
            <Link to="/"><Button variant="primary">Projects</Button></Link>
            <Link to="/settings"><Button>Voices and keys</Button></Link>
          </div>
        </div>
      </div>
    );
  }

  const step = (n: number, title: string, on: boolean, ok: boolean) => (
    <h2 className="flex items-center gap-2 font-semibold">
      <span className={`grid size-6 place-items-center rounded-full text-xs ${ok ? "bg-emerald-500 text-white" : on ? "bg-brand-600 text-white" : "bg-zinc-200 text-zinc-500 dark:bg-zinc-700"}`}>
        {ok ? <CheckCircle2 className="size-3.5" /> : n}
      </span>{title}
    </h2>
  );

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{first ? "Set up your narrator voice" : "Add a voice"}</h1>
        <p className="mt-1 text-sm text-zinc-500">
          {first ? "Voice Demo Lab narrates demos with Gemini text-to-speech. Add a Gemini API key, then pick one of your custom voices or a standard voice. This is saved for future sessions."
            : "Pair a saved key with another voice. You can switch between saved voices at any time."}
        </p>
      </div>
      {err && <Alert>{err}</Alert>}

      <section className="card space-y-4 p-5">
        {step(1, "Gemini API key", !keyId, !!keyId && !newKey)}
        {settings.key_source === "env" && <Alert tone="blue">$GEMINI_API_KEY is set in the environment, so it is used instead of the saved key for every call.</Alert>}
        {!newKey && settings.keys.length > 0 && (
          <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <Field label="Use a saved key" className="flex-1">
              <select className="input" value={keyId} onChange={(e) => { setKeyId(e.target.value); setVoice(null); }}>
                <option value="" disabled>Choose a key…</option>
                {settings.keys.map((k) => <option key={k.id} value={k.id}>{k.name} (…{k.hint})</option>)}
              </select>
            </Field>
            <Button icon={<Plus className="size-4" />} onClick={() => setNewKey(true)}>Add another key</Button>
          </div>
        )}
        {newKey && (
          <div className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Name" hint="To tell keys apart."><input className="input" value={keyName} onChange={(e) => setKeyName(e.target.value)} placeholder="My Gemini key" /></Field>
              <Field label="API key" className="sm:col-span-2" hint={<>From <a className="underline" href="https://aistudio.google.com/apikey" target="_blank" rel="noreferrer">aistudio.google.com/apikey</a>. For a custom voice, use a key from the project that created it.</>}>
                <input className="input font-mono" type="password" autoComplete="off" spellCheck={false} value={secret}
                  onChange={(e) => setSecret(e.target.value)} onKeyDown={(e) => e.key === "Enter" && secret.trim() && saveKey()} placeholder="AIza…" />
              </Field>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="flex items-start gap-2 text-xs text-zinc-500"><Lock className="mt-0.5 size-3.5 shrink-0" />
                Sent only to Voice Demo Lab on this computer, checked with Gemini, and saved in your system keychain. It is never shown again and never passes through the chat or the AI assistant.</p>
              <div className="flex gap-2">
                {settings.keys.length > 0 && <Button variant="ghost" onClick={() => setNewKey(false)}>Cancel</Button>}
                <Button variant="primary" icon={<KeyRound className="size-4" />} busy={busy === "key"} disabled={!secret.trim()} onClick={saveKey}>Check and save key</Button>
              </div>
            </div>
          </div>
        )}
      </section>

      <section className={`card space-y-4 p-5 ${keyId && !newKey ? "" : "pointer-events-none opacity-50"}`}>
        {step(2, "Choose a voice", !!keyId && !voice, !!voice)}
        {keyId && !newKey && <VoicePicker keyId={keyId} value={voice?.id ?? ""} onPick={(v) => { setVoice(v); setName(v.name); }} />}
      </section>

      <section className={`card space-y-4 p-5 ${voice ? "" : "pointer-events-none opacity-50"}`}>
        {step(3, "Label it and set the delivery", !!voice, false)}
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Label"><input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder={voice?.name} /></Field>
          <Field label="Description" className="sm:col-span-2" hint="When to use this voice. Your agent reads it to pick one, e.g. &quot;formal, for customer launches&quot;.">
            <input className="input" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Optional" />
          </Field>
          <Field label="Delivery style" className="sm:col-span-3" hint="How the narrator should sound. Projects can override it.">
            <input className="input" value={style} onChange={(e) => setStyle(e.target.value)} />
          </Field>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3">
          {voice && <PacingControl value={speed} onChange={setSpeed} with={{ key_id: keyId, voice: voice.id, style }} />}
          <Button variant="primary" className="ml-auto" icon={first ? <Mic className="size-4" /> : <ArrowRight className="size-4" />} busy={busy === "profile"} disabled={!voice} onClick={saveProfile}>
            {busy === "profile" ? "Saving and testing the voice…" : first ? "Save and finish" : "Save voice"}
          </Button>
        </div>
      </section>
    </div>
  );
}

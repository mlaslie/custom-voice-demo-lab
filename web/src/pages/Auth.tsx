import { CheckCircle2, Cloud, Eye, EyeOff, KeyRound, Lock, ShieldCheck, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { api, type Settings } from "../api";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { Alert, Badge, Button, Field } from "../components/ui";

type Provider = "aistudio" | "gcp";

export default function Auth({
  settings,
  onChange,
}: {
  settings: Settings | null;
  onChange: (s: Settings) => void;
}) {
  const [s, setS] = useState<Settings | null>(settings);
  const [provider, setProvider] = useState<Provider>("aistudio");
  const [keyLabel, setKeyLabel] = useState("");
  const [secret, setSecret] = useState("");
  const [showKey, setShowKey] = useState(false);
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState<{ tone: "red" | "blue"; text: string } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);

  useEffect(() => {
    api.settings().then((loaded) => {
      setS(loaded);
      onChange(loaded);
    }).catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (settings) setS(settings);
  }, [settings]);

  const updateSettings = (next: Settings) => {
    setS(next);
    onChange(next);
  };

  const run = async (name: string, fn: () => Promise<void>) => {
    setBusy(name);
    setMsg(null);
    try {
      await fn();
    } catch (e) {
      setMsg({ tone: "red", text: (e as Error).message });
    } finally {
      setBusy("");
    }
  };

  const handleAddKey = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!secret.trim()) return;
    await run("add-key", async () => {
      const label = keyLabel.trim() || "AI Studio Key";
      const res = await api.addKey(label, secret.trim());
      updateSettings(res.settings);
      setKeyLabel("");
      setSecret("");
      setShowKey(false);
      setMsg({
        tone: "blue",
        text: `Verified & saved "${res.key.name}" to OS keychain (${res.custom_voices} custom voice${res.custom_voices === 1 ? "" : "s"} found).`,
      });
    });
  };

  if (!s) return null;

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Authentication</h1>
        <p className="mt-0.5 text-xs text-zinc-500">
          Choose your backend provider and manage credentials stored safely in your OS keychain.
        </p>
      </div>

      {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}

      {/* Parent Provider Selector: AI Studio vs Google Cloud */}
      <fieldset className="space-y-2">
        <legend className="text-xs font-semibold">Authentication Provider</legend>
        <div className="grid gap-3 sm:grid-cols-2">
          <label
            htmlFor="auth-provider-aistudio"
            className={`flex cursor-pointer items-start gap-3 rounded-xl border p-4 transition ${
              provider === "aistudio"
                ? "border-brand-500 bg-brand-50/40 dark:bg-brand-700/15"
                : "border-zinc-200 bg-white hover:border-brand-500/60 dark:border-zinc-800 dark:bg-zinc-900"
            }`}
          >
            <input
              type="radio"
              id="auth-provider-aistudio"
              name="auth_provider"
              value="aistudio"
              checked={provider === "aistudio"}
              onChange={() => setProvider("aistudio")}
              className="mt-0.5 size-4 shrink-0"
            />
            <span className="space-y-1">
              <span className="flex items-center gap-2">
                <span className="text-sm font-semibold">AI Studio</span>
                <Badge tone="green">Active</Badge>
              </span>
              <span className="block text-xs text-zinc-500">
                Gemini API keys paired directly with your AI Studio custom voices.
              </span>
            </span>
          </label>

          <label
            htmlFor="auth-provider-gcp"
            className={`flex cursor-pointer items-start gap-3 rounded-xl border p-4 transition ${
              provider === "gcp"
                ? "border-brand-500 bg-brand-50/40 dark:bg-brand-700/15"
                : "border-zinc-200 bg-white hover:border-brand-500/60 dark:border-zinc-800 dark:bg-zinc-900"
            }`}
          >
            <input
              type="radio"
              id="auth-provider-gcp"
              name="auth_provider"
              value="gcp"
              checked={provider === "gcp"}
              onChange={() => setProvider("gcp")}
              className="mt-0.5 size-4 shrink-0"
            />
            <span className="space-y-1">
              <span className="flex items-center gap-2">
                <span className="text-sm font-semibold">Google Cloud</span>
                <Badge tone="zinc">Coming Soon</Badge>
              </span>
              <span className="block text-xs text-zinc-500">
                Enterprise Vertex AI project, IAM &amp; Application Default Credentials.
              </span>
            </span>
          </label>
        </div>
      </fieldset>

      {provider === "aistudio" ? (
        <div className="space-y-4">
          {s.key_source === "env" && (
            <Alert tone="blue">
              <code>$GEMINI_API_KEY</code> is set in the environment and overrides saved keychain keys.
            </Alert>
          )}

          <section className="card overflow-hidden">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
              <h2 className="flex items-center gap-2 text-sm font-semibold">
                <KeyRound className="size-4 text-brand-600" /> Saved AI Studio API Keys
              </h2>
              <span className="inline-flex items-center gap-1.5 text-xs text-zinc-500">
                <Lock className="size-3.5" /> Stored in OS Keychain · Never sent to chat
              </span>
            </div>

            <div className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {!s.keys.length && (
                <div className="p-4 text-xs text-zinc-500">No AI Studio keys saved yet. Add one below.</div>
              )}
              {s.keys.map((k) => {
                const usedCount = s.profiles.filter((v) => v.key_id === k.id).length;
                return (
                  <div key={k.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                    <div className="min-w-0 space-y-0.5">
                      <div className="text-sm font-medium">{k.name}</div>
                      <div className="font-mono text-xs text-zinc-500">
                        ••••••••{k.hint} · {usedCount} voice{usedCount === 1 ? "" : "s"}
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <Button
                        size="sm"
                        variant="secondary"
                        busy={busy === `verify:${k.id}`}
                        icon={<ShieldCheck className="size-3.5" />}
                        onClick={() =>
                          run(`verify:${k.id}`, async () => {
                            const r = await api.verifyKey(k.id);
                            setMsg({
                              tone: "blue",
                              text: `Verified "${k.name}" (${r.custom_voices} custom, ${r.standard_voices} standard voices).`,
                            });
                          })
                        }
                      >
                        Verify
                      </Button>
                      <Button
                        size="sm"
                        variant="danger"
                        disabled={usedCount > 0}
                        title={usedCount > 0 ? "Delete voices using this key in Voice Lab first" : "Remove key"}
                        icon={<Trash2 className="size-3.5" />}
                        onClick={() => setDeleteTarget({ id: k.id, name: k.name })}
                      >
                        Delete
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          </section>

          <form onSubmit={handleAddKey} className="card space-y-3 p-4">
            <h2 className="text-sm font-semibold">Add AI Studio API Key</h2>
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="Key label">
                <input
                  className="input"
                  value={keyLabel}
                  onChange={(e) => setKeyLabel(e.target.value)}
                  placeholder="e.g. Production AI Studio"
                />
              </Field>
              <Field
                label="Gemini API key"
                className="sm:col-span-2"
                hint={
                  <>
                    Create a key at{" "}
                    <a
                      href="https://aistudio.google.com/apikey"
                      target="_blank"
                      rel="noreferrer"
                      className="underline"
                    >
                      aistudio.google.com/apikey
                    </a>
                    .
                  </>
                }
              >
                <div className="flex gap-2">
                  <input
                    className="input font-mono"
                    type={showKey ? "text" : "password"}
                    required
                    autoComplete="off"
                    autoCorrect="off"
                    autoCapitalize="none"
                    spellCheck={false}
                    value={secret}
                    onChange={(e) => setSecret(e.target.value)}
                    placeholder="AIza…"
                  />
                  <Button
                    type="button"
                    variant="secondary"
                    aria-pressed={showKey}
                    onClick={() => setShowKey((v) => !v)}
                    icon={showKey ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                  >
                    {showKey ? "Hide" : "Show"}
                  </Button>
                </div>
              </Field>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
              <span className="text-xs text-zinc-500">
                Only the key label and last four characters appear after saving.
              </span>
              <Button
                type="submit"
                variant="primary"
                busy={busy === "add-key"}
                disabled={!secret.trim()}
                icon={<CheckCircle2 className="size-4" />}
              >
                Verify &amp; Save to Keychain
              </Button>
            </div>
          </form>
        </div>
      ) : (
        <section className="card space-y-3 p-8 text-center">
          <div className="mx-auto grid size-12 place-items-center rounded-2xl bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
            <Cloud className="size-6" />
          </div>
          <div>
            <Badge tone="zinc">Coming Soon</Badge>
          </div>
          <h2 className="text-base font-semibold">Google Cloud / Vertex AI Authentication</h2>
          <p className="mx-auto max-w-md text-xs leading-relaxed text-zinc-500">
            Direct integration with Google Cloud projects, Vertex AI regional endpoints, and{" "}
            <code>gcloud auth application-default</code> is planned for a future update.
          </p>
          <div className="pt-1">
            <Button variant="primary" size="sm" onClick={() => setProvider("aistudio")}>
              Use AI Studio Keys
            </Button>
          </div>
        </section>
      )}

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="Remove AI Studio key"
        body={`Remove "${deleteTarget?.name || ""}" from your OS keychain?`}
        confirmLabel="Remove Key"
        busy={busy === "delete-key"}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (!deleteTarget) return;
          const id = deleteTarget.id;
          run("delete-key", async () => {
            updateSettings(await api.deleteKey(id));
            setDeleteTarget(null);
            setMsg({ tone: "blue", text: "Key removed from OS keychain." });
          });
        }}
      />
    </div>
  );
}

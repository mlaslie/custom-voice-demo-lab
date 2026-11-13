import { FolderOpen, Save } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Settings } from "../api";
import { PacingControl } from "../components/PacingControl";
import { Alert, Button, Field } from "../components/ui";

const STYLE_CHIPS = [
  {
    label: "Product Narrator",
    style: "clear, warm, confident product-demo narrator; unhurried pace",
  },
  {
    label: "Executive Briefing",
    style: "authoritative executive briefing, crisp and composed",
  },
  {
    label: "Developer Walkthrough",
    style: "energetic developer walkthrough, upbeat and conversational",
  },
];

export default function SettingsPage({ onChange }: { onChange: (s: Settings) => void }) {
  const [s, setS] = useState<Settings | null>(null);
  const [models, setModels] = useState<string[]>([]);
  const [selectedProfileId, setSelectedProfileId] = useState("");
  const [voiceStyle, setVoiceStyle] = useState("");
  const [voiceSpeed, setVoiceSpeed] = useState(1.0);
  const [voiceNote, setVoiceNote] = useState("");
  const [outputDir, setOutputDir] = useState("");
  const [defaultRes, setDefaultRes] = useState<"1080p" | "4k">("1080p");
  const [audience, setAudience] = useState("");
  const [ttsModel, setTtsModel] = useState("");
  const [busy, setBusy] = useState("");
  const [msg, setMsg] = useState<{ tone: "red" | "blue"; text: string } | null>(null);

  const hydrate = (next: Settings, preferId?: string) => {
    setS(next);
    onChange(next);
    const pid =
      preferId && next.profiles.some((v) => v.id === preferId)
        ? preferId
        : next.active_profile || next.profiles[0]?.id || "";
    setSelectedProfileId(pid);
    const prof = next.profiles.find((v) => v.id === pid) ?? next.active;
    if (prof) {
      setVoiceStyle(prof.style);
      setVoiceSpeed(prof.speed);
      setVoiceNote(prof.description);
    }
    setOutputDir(next.output_dir);
    setDefaultRes(next.default_resolution || "1080p");
    setAudience(next.audience);
    setTtsModel(next.tts_model);
  };

  useEffect(() => {
    api.settings().then((loaded) => hydrate(loaded)).catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (s && !s.setup_needed) {
      api
        .models()
        .then((m) => setModels(m.filter((x) => x.methods.includes("generateContent")).map((x) => x.name)))
        .catch(() => {});
    }
  }, [s?.setup_needed]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!s) return null;

  const handleVoicePick = (pid: string) => {
    setSelectedProfileId(pid);
    const prof = s.profiles.find((v) => v.id === pid);
    if (prof) {
      setVoiceStyle(prof.style);
      setVoiceSpeed(prof.speed);
      setVoiceNote(prof.description);
    }
  };

  const handleBrowseOutput = async () => {
    setMsg(null);
    setBusy("browse");
    try {
      const r = await api.chooseOutputDir();
      if (!r.canceled && r.path) {
        setOutputDir(r.path);
      }
    } catch (e) {
      setMsg({ tone: "red", text: (e as Error).message });
    } finally {
      setBusy("");
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy("save");
    setMsg(null);
    try {
      let latest = await api.saveSettings({
        output_dir: outputDir.trim() || s.output_dir,
        default_resolution: defaultRes,
        audience,
        tts_model: ttsModel.trim() || s.tts_model,
      });

      if (selectedProfileId) {
        if (selectedProfileId !== latest.active_profile) {
          latest = await api.activateProfile(selectedProfileId);
        }
        latest = await api.patchProfile(selectedProfileId, {
          style: voiceStyle,
          speed: voiceSpeed,
          description: voiceNote.trim(),
        });
      }

      hydrate(latest, selectedProfileId);
      setMsg({
        tone: "blue",
        text: `Settings saved${latest.active ? ` (Default voice: ${latest.active.name} at ${latest.active.speed.toFixed(2)}×)` : ""}.`,
      });
    } catch (e2) {
      setMsg({ tone: "red", text: (e2 as Error).message });
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Settings</h1>
        <p className="mt-0.5 text-xs text-zinc-500">
          Configure your default narrator voice, delivery style, speed/pace, usage note, output path, resolution, and default audience.
        </p>
      </div>

      {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}

      <form onSubmit={handleSave} className="space-y-4">
        {/* Default Voice & Delivery */}
        <section className="card space-y-4 p-4 sm:p-5">
          <h2 className="text-sm font-semibold">Default Voice &amp; Delivery</h2>

          {!s.profiles.length ? (
            <Alert tone="blue">
              No voice profiles yet. Create or pair one on the{" "}
              <Link to="/voice-lab" className="font-semibold underline">
                Voice Lab tab
              </Link>
              .
            </Alert>
          ) : (
            <>
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label="Default voice to use">
                  <select
                    className="input"
                    value={selectedProfileId}
                    onChange={(e) => handleVoicePick(e.target.value)}
                  >
                    {s.profiles.map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.name} ({v.kind === "custom" ? "Custom" : "Standard"})
                      </option>
                    ))}
                  </select>
                </Field>

                <div className="space-y-1.5">
                  <Field label="Delivery style">
                    <input
                      className="input"
                      value={voiceStyle}
                      onChange={(e) => setVoiceStyle(e.target.value)}
                      placeholder="clear, warm, confident product-demo narrator; unhurried pace"
                    />
                  </Field>
                  <div className="flex flex-wrap gap-1.5">
                    {STYLE_CHIPS.map((c) => (
                      <button
                        key={c.label}
                        type="button"
                        onClick={() => setVoiceStyle(c.style)}
                        className="rounded-md border border-zinc-200 bg-zinc-50 px-2 py-0.5 text-xs text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-300 dark:hover:bg-zinc-800"
                      >
                        {c.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              <div className="rounded-xl border border-zinc-200 bg-zinc-50/70 p-3.5 dark:border-zinc-800 dark:bg-zinc-950">
                <PacingControl
                  label="Speed / Pace"
                  value={voiceSpeed}
                  onChange={setVoiceSpeed}
                  with={{
                    profile_id: selectedProfileId,
                    style: voiceStyle,
                  }}
                />
              </div>

              <Field
                label="When to use this voice (note / description)"
                hint="Helps Antigravity decide automatically when to choose this voice profile."
              >
                <textarea
                  className="input min-h-16"
                  value={voiceNote}
                  onChange={(e) => setVoiceNote(e.target.value)}
                  placeholder="Default voice for executive product demos, release briefings, and architecture walkthroughs."
                />
              </Field>
            </>
          )}
        </section>

        {/* Output Path, Resolution & Audience */}
        <section className="card space-y-4 p-4 sm:p-5">
          <h2 className="text-sm font-semibold">Output Path, Resolution &amp; Audience</h2>

          <Field label="Output path" hint="Rendered MP4 videos and frame caches are saved here.">
            <div className="flex gap-2">
              <input
                className="input font-mono"
                value={outputDir}
                onChange={(e) => setOutputDir(e.target.value)}
                autoCorrect="off"
                autoCapitalize="none"
                spellCheck={false}
              />
              <Button
                type="button"
                variant="secondary"
                busy={busy === "browse"}
                icon={<FolderOpen className="size-4" />}
                onClick={handleBrowseOutput}
              >
                Browse…
              </Button>
            </div>
          </Field>

          <fieldset className="space-y-2">
            <legend className="label">Default video resolution</legend>
            <div className="flex flex-wrap gap-3">
              <label
                htmlFor="default-res-1080p"
                className="flex cursor-pointer items-center gap-2 rounded-lg border border-zinc-300 px-3 py-2 text-xs dark:border-zinc-700"
              >
                <input
                  type="radio"
                  id="default-res-1080p"
                  name="default-resolution"
                  value="1080p"
                  checked={defaultRes === "1080p"}
                  onChange={() => setDefaultRes("1080p")}
                />
                <span>1080p · Full HD (1920×1080)</span>
              </label>
              <label
                htmlFor="default-res-4k"
                className="flex cursor-pointer items-center gap-2 rounded-lg border border-zinc-300 px-3 py-2 text-xs dark:border-zinc-700"
              >
                <input
                  type="radio"
                  id="default-res-4k"
                  name="default-resolution"
                  value="4k"
                  checked={defaultRes === "4k"}
                  onChange={() => setDefaultRes("4k")}
                />
                <span>4K · Ultra HD (3840×2160)</span>
              </label>
            </div>
          </fieldset>

          <Field
            label="Default audience for video"
            hint="Shapes narration depth, tone, and how much background context each script includes."
          >
            <textarea
              className="input min-h-16"
              value={audience}
              onChange={(e) => setAudience(e.target.value)}
            />
          </Field>

          <Field
            label="Text-to-speech model"
            hint="Your coding agent writes scripts; this Gemini model synthesizes voice narration."
          >
            <input
              className="input font-mono"
              value={ttsModel}
              onChange={(e) => setTtsModel(e.target.value)}
              list="models"
            />
          </Field>
          <datalist id="models">
            {models.map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
        </section>

        <div className="flex justify-end">
          <Button type="submit" variant="primary" busy={busy === "save"} icon={<Save className="size-4" />}>
            Save Settings
          </Button>
        </div>
      </form>
    </div>
  );
}

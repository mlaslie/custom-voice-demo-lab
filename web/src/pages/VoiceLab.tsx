import {
  CheckCircle2,
  Mic,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Sparkles,
  Square,
  Trash2,
  Upload,
  Volume2,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, type AudioInputDevice, type Settings, type Voice } from "../api";
import { ConfirmDialog } from "../components/ConfirmDialog";
import { HalVoiceMeter, type RemoteMicTelemetry } from "../components/HalVoiceMeter";
import { PacingControl } from "../components/PacingControl";
import { VerifyStatus } from "../components/VerifyStatus";
import { SAMPLE, VoicePicker } from "../components/VoicePicker";
import { playClip, stopClip, VoiceButton } from "../components/hooks";
import { Alert, Badge, Button, Field } from "../components/ui";

const CONSENT_PHRASE =
  "I am the owner of this voice and I consent to Google using this voice to create a synthetic voice model.";
const CALIBRATION_SCRIPT =
  "Welcome to today's product architecture walkthrough. Over the next few minutes, we'll explore how engineering teams design, evaluate, and ship reliable AI workflows from a single unified studio. Along the way, we'll compare real-world latency, throughput, and cost per task, review key security guardrails, and walk step by step through a live production deployment from start to finish.";
const DEFAULT_STYLE = "clear, warm, confident product-demo narrator; unhurried pace";
const DEVICE_STORAGE_KEY = "demolab_audio_device_id";

type RecTarget = "consent" | "sample" | null;
interface RecordedClip {
  b64: string;
  blob: Blob | null;
  secs: number;
}

function base64WavToBlob(b64: string): Blob {
  const binary = atob(b64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return new Blob([bytes], { type: "audio/wav" });
}

function readFileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const raw = typeof reader.result === "string" ? reader.result : "";
      const comma = raw.indexOf(",");
      resolve(comma >= 0 ? raw.slice(comma + 1) : raw);
    };
    reader.onerror = () => reject(new Error("Could not read selected audio file."));
    reader.readAsDataURL(file);
  });
}

export default function VoiceLab({
  settings,
  onChange,
}: {
  settings: Settings | null;
  onChange: (s: Settings) => void;
}) {
  const [s, setS] = useState<Settings | null>(settings);
  const [msg, setMsg] = useState<{ tone: "red" | "blue"; text: string } | null>(null);
  const [busy, setBusy] = useState("");
  const [mode, setMode] = useState<"create" | "pair">("create");

  // Create new custom voice state
  const [keyId, setKeyId] = useState(settings?.keys[0]?.id ?? "");
  const [voiceName, setVoiceName] = useState("");
  const [description, setDescription] = useState("");
  const [consentClip, setConsentClip] = useState<RecordedClip | null>(null);
  const [sampleClip, setSampleClip] = useState<RecordedClip | null>(null);
  const [playingTarget, setPlayingTarget] = useState<RecTarget>(null);

  // Local OS recording device + live HAL 9000 telemetry
  const [audioDevices, setAudioDevices] = useState<AudioInputDevice[]>([]);
  const [loadingDevices, setLoadingDevices] = useState(false);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>(() => {
    try {
      return localStorage.getItem(DEVICE_STORAGE_KEY) || "";
    } catch {
      return "";
    }
  });
  const [recTarget, setRecTarget] = useState<RecTarget>(null);
  const [testingMic, setTestingMic] = useState(false);
  const [liveTelemetry, setLiveTelemetry] = useState<RemoteMicTelemetry | null>(null);
  const [recElapsed, setRecElapsed] = useState(0);
  const activeCaptureRef = useRef(false);
  const pollingTimerRef = useRef<number | null>(null);
  const pollingInFlightRef = useRef(false);

  // Pair existing voice state
  const [pickedVoice, setPickedVoice] = useState<Voice | null>(null);
  const [pairStyle, setPairStyle] = useState(DEFAULT_STYLE);
  const [pairSpeed, setPairSpeed] = useState(1);

  // Delete confirmation modal state
  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string; isCustom: boolean } | null>(null);

  const loadAudioDevices = async () => {
    setLoadingDevices(true);
    try {
      const res = await api.audioDevices();
      setAudioDevices(res.devices);
      setSelectedDeviceId((prev) => {
        const chosen =
          prev && res.devices.some((d) => d.id === prev)
            ? prev
            : res.recommended_id || res.devices[0]?.id || "";
        try {
          if (chosen) localStorage.setItem(DEVICE_STORAGE_KEY, chosen);
        } catch {
          /* ignore */
        }
        return chosen;
      });
    } catch {
      /* ignore */
    } finally {
      setLoadingDevices(false);
    }
  };

  useEffect(() => {
    api.settings().then((loaded) => {
      setS(loaded);
      onChange(loaded);
    }).catch(() => {});
    loadAudioDevices().catch(() => {});
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (settings) setS(settings);
  }, [settings]);

  useEffect(() => {
    if (!s?.keys.length) return;
    if (!keyId || !s.keys.some((k) => k.id === keyId)) {
      setKeyId(s.keys[0].id);
    }
  }, [s?.keys, keyId]);

  const stopPolling = () => {
    if (pollingTimerRef.current !== null) {
      window.clearInterval(pollingTimerRef.current);
      pollingTimerRef.current = null;
    }
    pollingInFlightRef.current = false;
  };

  useEffect(() => {
    return () => {
      stopPolling();
      stopClip();
      if (activeCaptureRef.current) {
        api.stopAudioCapture().catch(() => {});
        activeCaptureRef.current = false;
      }
    };
  }, []);

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

  const startPolling = () => {
    stopPolling();
    pollingTimerRef.current = window.setInterval(async () => {
      if (pollingInFlightRef.current) return;
      pollingInFlightRef.current = true;
      try {
        const st = await api.audioCaptureStatus();
        setLiveTelemetry({
          active: st.active,
          db: st.db,
          energy: st.energy,
          bands: st.bands,
          deviceName: st.device_name,
          digitalSilence: st.digital_silence,
          error: st.error,
        });
        setRecElapsed(Math.floor(st.elapsed));
        if (!st.active && st.error) {
          stopPolling();
          activeCaptureRef.current = false;
          setRecTarget(null);
          setTestingMic(false);
          setMsg({ tone: "red", text: st.error });
        }
      } catch {
        /* ignore transient poll failures */
      } finally {
        pollingInFlightRef.current = false;
      }
    }, 80);
  };

  const handleSelectDevice = async (nextId: string) => {
    setSelectedDeviceId(nextId);
    try {
      localStorage.setItem(DEVICE_STORAGE_KEY, nextId);
    } catch {
      /* ignore */
    }
    if (testingMic) {
      try {
        const st = await api.startAudioCapture(nextId, false);
        activeCaptureRef.current = true;
        setLiveTelemetry({
          active: st.active,
          db: st.db,
          energy: st.energy,
          bands: st.bands,
          deviceName: st.device_name,
          digitalSilence: st.digital_silence,
          error: st.error,
        });
      } catch (e) {
        setMsg({ tone: "red", text: (e as Error).message || "Could not switch recording device." });
      }
    }
  };

  const handleToggleTestMic = async () => {
    setMsg(null);
    if (testingMic) {
      stopPolling();
      setTestingMic(false);
      setLiveTelemetry(null);
      activeCaptureRef.current = false;
      await api.stopAudioCapture().catch(() => {});
      return;
    }
    stopClip();
    setPlayingTarget(null);
    try {
      const st = await api.startAudioCapture(selectedDeviceId, false);
      activeCaptureRef.current = true;
      setTestingMic(true);
      setRecElapsed(0);
      setLiveTelemetry({
        active: st.active,
        db: st.db,
        energy: st.energy,
        bands: st.bands,
        deviceName: st.device_name,
        digitalSilence: st.digital_silence,
        error: st.error,
      });
      startPolling();
    } catch (e) {
      setMsg({ tone: "red", text: (e as Error).message || "Could not start live microphone test." });
    }
  };

  const stopRecording = async () => {
    const target = recTarget;
    stopPolling();
    setRecTarget(null);
    setLiveTelemetry(null);
    setBusy("stop-capture");
    try {
      const res = await api.stopAudioCapture();
      activeCaptureRef.current = false;
      if (!res.ok || !res.audio_b64) {
        setMsg({
          tone: "red",
          text: res.error || "No audio was captured from the selected microphone.",
        });
        return;
      }
      const clip: RecordedClip = {
        b64: res.audio_b64,
        blob: base64WavToBlob(res.audio_b64),
        secs: Math.max(1, Math.round(res.seconds)),
      };
      if (target === "consent") {
        setConsentClip(clip);
      } else if (target === "sample") {
        setSampleClip(clip);
      }
      if (res.digital_silence) {
        setMsg({
          tone: "red",
          text: `${res.device_name || "Selected device"} recorded digital silence (0 signal). Pick an active Recording Input Device above and re-record.`,
        });
      }
    } catch (e) {
      activeCaptureRef.current = false;
      setMsg({ tone: "red", text: (e as Error).message || "Failed to finalize recording." });
    } finally {
      setBusy("");
    }
  };

  const startRecording = async (target: "consent" | "sample") => {
    setMsg(null);
    if (recTarget) {
      await stopRecording();
      return;
    }
    stopClip();
    setPlayingTarget(null);
    setTestingMic(false);
    try {
      const st = await api.startAudioCapture(selectedDeviceId, true);
      activeCaptureRef.current = true;
      setRecTarget(target);
      setRecElapsed(0);
      setLiveTelemetry({
        active: st.active,
        db: st.db,
        energy: st.energy,
        bands: st.bands,
        deviceName: st.device_name,
        digitalSilence: st.digital_silence,
        error: st.error,
      });
      startPolling();
    } catch (e) {
      activeCaptureRef.current = false;
      setRecTarget(null);
      setMsg({ tone: "red", text: (e as Error).message || "Could not start microphone recording." });
    }
  };

  const togglePreviewClip = (target: "sample" | "consent") => {
    if (playingTarget === target) {
      stopClip();
      setPlayingTarget(null);
      return;
    }
    const clip = target === "sample" ? sampleClip : consentClip;
    if (!clip?.blob) return;
    setPlayingTarget(target);
    playClip(clip.blob, () => {
      setPlayingTarget((cur) => (cur === target ? null : cur));
    });
  };

  const handleFileUpload = (target: "consent" | "sample") => async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    try {
      const b64 = await readFileAsBase64(file);
      const clip: RecordedClip = { b64, blob: file, secs: 0 };
      if (target === "consent") {
        setConsentClip(clip);
      } else {
        setSampleClip(clip);
      }
    } catch (err) {
      setMsg({ tone: "red", text: (err as Error).message });
    }
  };

  const handleCreateCustomVoice = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!keyId) {
      setMsg({ tone: "red", text: "Add an AI Studio key on the Auth tab first." });
      return;
    }
    if (!voiceName.trim()) {
      setMsg({ tone: "red", text: "Enter a name for your custom voice." });
      return;
    }
    if (!consentClip || !sampleClip) {
      setMsg({ tone: "red", text: "Record (or upload) both the reference calibration sample and consent statement first." });
      return;
    }
    await run("create-voice", async () => {
      const res = await api.createCustomVoice({
        key_id: keyId,
        name: voiceName.trim(),
        description: description.trim(),
        style: DEFAULT_STYLE,
        speed: 1.0,
        activate: true,
        source_audio_b64: sampleClip.b64,
        consent_audio_b64: consentClip.b64,
      });
      updateSettings(res.settings);
      setVoiceName("");
      setDescription("");
      setConsentClip(null);
      setSampleClip(null);
      setMsg({ tone: "blue", text: `Created and verified custom voice "${res.voice.name}".` });
    });
  };

  const handlePairExisting = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!keyId || !pickedVoice) return;
    await run("pair-voice", async () => {
      const next = await api.addProfile({
        name: voiceName.trim() || pickedVoice.name,
        description: description.trim(),
        key_id: keyId,
        voice: pickedVoice.id,
        voice_name: pickedVoice.name,
        kind: pickedVoice.kind,
        style: pairStyle,
        speed: pairSpeed,
        activate: true,
      });
      updateSettings(next);
      setVoiceName("");
      setDescription("");
      setPickedVoice(null);
      setMsg({ tone: "blue", text: `Saved narrator voice "${pickedVoice.name}".` });
    });
  };

  if (!s) return null;
  const keyHint = (id: string) => {
    const k = s.keys.find((x) => x.id === id);
    return k ? `${k.name} (••••${k.hint})` : "missing key";
  };

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Voice Lab</h1>
          <p className="mt-0.5 text-xs text-zinc-500">
            List, create, set default, and delete Gemini TTS custom and standard narrator voices.
          </p>
        </div>
        <span className="rounded-lg border border-zinc-200 bg-white px-2.5 py-1 text-xs font-medium dark:border-zinc-800 dark:bg-zinc-900">
          Saved voices: <strong>{s.profiles.length}</strong>
        </span>
      </div>

      {msg && <Alert tone={msg.tone}>{msg.text}</Alert>}

      {!s.keys.length && (
        <Alert tone="amber">
          Add an AI Studio API key on the{" "}
          <Link to="/auth" className="font-semibold underline">
            Auth tab
          </Link>{" "}
          before creating or verifying voices.
        </Alert>
      )}

      {/* Saved Voices List */}
      <section className="card overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
          <h2 className="flex items-center gap-2 text-sm font-semibold">
            <Volume2 className="size-4 text-brand-600" />
            Your Custom &amp; Saved Voices
          </h2>
          <span className="text-xs text-zinc-500">Synced with AI Studio project</span>
        </div>

        <div className="divide-y divide-zinc-100 dark:divide-zinc-800">
          {!s.profiles.length && (
            <div className="p-5 text-xs text-zinc-500">
              No voice profiles saved yet. Record a new custom voice or pair an existing one below.
            </div>
          )}

          {s.profiles.map((v) => {
            const isDefault = v.id === s.active_profile;
            return (
              <div key={v.id} className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
                <div className="min-w-0 flex-1 space-y-0.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-semibold">{v.name}</span>
                    <Badge tone={v.kind === "custom" ? "violet" : "zinc"}>{v.kind}</Badge>
                    <VerifyStatus profile={v} onChange={updateSettings} />
                    {isDefault ? (
                      <Badge tone="blue">Default</Badge>
                    ) : (
                      <button
                        type="button"
                        onClick={() => run("activate", async () => updateSettings(await api.activateProfile(v.id)))}
                        className="rounded-md border border-zinc-300 px-2 py-0.5 text-xs font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:text-zinc-200 dark:hover:bg-zinc-800"
                      >
                        Set Default
                      </button>
                    )}
                  </div>
                  <div className="truncate font-mono text-xs text-zinc-500">
                    {v.voice} · {keyHint(v.key_id)}
                  </div>
                  {v.description && (
                    <p className="truncate text-xs text-zinc-500">{v.description}</p>
                  )}
                </div>

                <div className="flex items-center gap-1.5">
                  <VoiceButton text={SAMPLE} with={{ profile_id: v.id }} label="Play Sample" />
                  <Button
                    size="sm"
                    variant="danger"
                    title="Delete voice"
                    onClick={() =>
                      setDeleteTarget({ id: v.id, name: v.name, isCustom: v.kind === "custom" })
                    }
                    icon={<Trash2 className="size-3.5" />}
                  >
                    Delete
                  </Button>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* Create New Custom Voice / Pair Existing Voice */}
      <section className="card space-y-4 p-4 sm:p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold">Add Voice</h2>
            <p className="text-xs text-zinc-500">
              Record a new Gemini custom voice clone with live HAL 9000 telemetry or pair an existing AI Studio / standard voice.
            </p>
          </div>
          <div className="inline-flex rounded-lg border border-zinc-200 bg-zinc-50 p-0.5 dark:border-zinc-800 dark:bg-zinc-950">
            <button
              type="button"
              onClick={() => setMode("create")}
              className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition ${
                mode === "create"
                  ? "bg-brand-600 text-white shadow-sm"
                  : "text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
              }`}
            >
              <Mic className="size-3.5" /> Create Custom Voice
            </button>
            <button
              type="button"
              onClick={() => setMode("pair")}
              className={`inline-flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-medium transition ${
                mode === "pair"
                  ? "bg-brand-600 text-white shadow-sm"
                  : "text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
              }`}
            >
              <Sparkles className="size-3.5" /> Pair Existing Voice
            </button>
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Voice profile name">
            <input
              className="input"
              value={voiceName}
              onChange={(e) => setVoiceName(e.target.value)}
              placeholder={mode === "create" ? "e.g. Executive Keynote Voice" : pickedVoice?.name || "My narrator voice"}
            />
          </Field>
          <Field label="Target AI Studio key">
            <select
              className="input"
              value={keyId}
              onChange={(e) => {
                setKeyId(e.target.value);
                setPickedVoice(null);
              }}
              disabled={!s.keys.length}
            >
              {!s.keys.length && <option value="">No AI Studio keys saved</option>}
              {s.keys.map((k) => (
                <option key={k.id} value={k.id}>
                  {k.name} (••••{k.hint})
                </option>
              ))}
            </select>
          </Field>
        </div>

        {mode === "create" ? (
          <form onSubmit={handleCreateCustomVoice} className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Recording input device (local system)" hint="Captures directly from the chosen OS microphone.">
                <div className="flex items-center gap-2">
                  <select
                    className="input"
                    aria-label="Recording input device"
                    value={selectedDeviceId}
                    disabled={recTarget !== null || (!audioDevices.length && loadingDevices)}
                    onChange={(e) => handleSelectDevice(e.target.value)}
                  >
                    {!audioDevices.length && <option value="">Detecting local microphones…</option>}
                    {audioDevices.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.name}
                        {d.recommended ? " (Recommended)" : ""}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={() => loadAudioDevices()}
                    disabled={loadingDevices || recTarget !== null}
                    title="Refresh local microphones"
                    className="inline-flex h-9 shrink-0 items-center gap-1 rounded-lg border border-zinc-300 bg-white px-2.5 text-xs font-medium text-zinc-700 hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800"
                  >
                    <RefreshCw className={`size-3.5 ${loadingDevices ? "animate-spin" : ""}`} />
                    Refresh
                  </button>
                </div>
              </Field>

              <Field label="When to use this voice (optional)" hint="Helps Antigravity decide automatically when to pick this voice.">
                <input
                  className="input"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="e.g. executive product demos and release briefings"
                />
              </Field>
            </div>

            <div className="grid gap-3 md:grid-cols-2">
              {/* Step 1: Reference calibration speech sample */}
              <div className="flex flex-col justify-between gap-2 rounded-xl border border-zinc-200 p-3.5 dark:border-zinc-800">
                <div className="space-y-2">
                  <div className="flex items-center justify-between gap-2 text-xs">
                    <span className="font-semibold">1. Reference Calibration Sample</span>
                    {sampleClip ? (
                      sampleClip.secs > 0 && sampleClip.secs < 20 ? (
                        <span className="font-medium text-amber-600 dark:text-amber-400">
                          Recorded ({sampleClip.secs}s · 20s+ min recommended)
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 font-medium text-emerald-600 dark:text-emerald-400">
                          <CheckCircle2 className="size-3.5" /> Ready{sampleClip.secs ? ` (${sampleClip.secs}s)` : ""}
                        </span>
                      )
                    ) : (
                      <span className="text-zinc-500">Min 20s clear speech</span>
                    )}
                  </div>
                  <p className="text-xs leading-relaxed text-zinc-600 dark:text-zinc-300">“{CALIBRATION_SCRIPT}”</p>
                </div>
                <div className="flex flex-wrap items-center gap-2 pt-1">
                  <Button
                    type="button"
                    size="sm"
                    variant={recTarget === "sample" ? "danger" : "secondary"}
                    disabled={(recTarget !== null && recTarget !== "sample") || busy === "stop-capture"}
                    onClick={() => (recTarget === "sample" ? stopRecording() : startRecording("sample"))}
                    icon={recTarget === "sample" ? <Square className="size-3.5" /> : <Mic className="size-3.5" />}
                  >
                    {recTarget === "sample"
                      ? `Stop (${recElapsed}s / 20s+)`
                      : sampleClip
                        ? "Re-record Sample"
                        : "Record Sample"}
                  </Button>
                  {sampleClip?.blob && recTarget !== "sample" && (
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={() => togglePreviewClip("sample")}
                      icon={playingTarget === "sample" ? <Pause className="size-3.5" /> : <Play className="size-3.5" />}
                    >
                      {playingTarget === "sample" ? "Stop" : "Play"}
                    </Button>
                  )}
                  <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-zinc-300 bg-white px-2.5 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800">
                    <Upload className="size-3.5" />
                    Upload WAV
                    <input type="file" accept="audio/*" className="visually-hidden" onChange={handleFileUpload("sample")} />
                  </label>
                </div>
              </div>

              {/* Step 2: Consent recording */}
              <div className="flex flex-col justify-between gap-2 rounded-xl border border-zinc-200 p-3.5 dark:border-zinc-800">
                <div className="space-y-2">
                  <div className="flex items-center justify-between gap-2 text-xs">
                    <span className="font-semibold">2. Consent Statement</span>
                    {consentClip ? (
                      <span className="inline-flex items-center gap-1 font-medium text-emerald-600 dark:text-emerald-400">
                        <CheckCircle2 className="size-3.5" /> Ready{consentClip.secs ? ` (${consentClip.secs}s)` : ""}
                      </span>
                    ) : (
                      <span className="text-zinc-500">Required by Gemini</span>
                    )}
                  </div>
                  <p className="text-xs leading-relaxed text-zinc-600 dark:text-zinc-300">“{CONSENT_PHRASE}”</p>
                </div>
                <div className="flex flex-wrap items-center gap-2 pt-1">
                  <Button
                    type="button"
                    size="sm"
                    variant={recTarget === "consent" ? "danger" : "secondary"}
                    disabled={(recTarget !== null && recTarget !== "consent") || busy === "stop-capture"}
                    onClick={() => (recTarget === "consent" ? stopRecording() : startRecording("consent"))}
                    icon={recTarget === "consent" ? <Square className="size-3.5" /> : <Mic className="size-3.5" />}
                  >
                    {recTarget === "consent"
                      ? `Stop (${recElapsed}s)`
                      : consentClip
                        ? "Re-record Consent"
                        : "Record Consent"}
                  </Button>
                  {consentClip?.blob && recTarget !== "consent" && (
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={() => togglePreviewClip("consent")}
                      icon={playingTarget === "consent" ? <Pause className="size-3.5" /> : <Play className="size-3.5" />}
                    >
                      {playingTarget === "consent" ? "Stop" : "Play"}
                    </Button>
                  )}
                  <label className="inline-flex cursor-pointer items-center gap-1.5 rounded-lg border border-zinc-300 bg-white px-2.5 py-1.5 text-xs font-medium text-zinc-700 hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-200 dark:hover:bg-zinc-800">
                    <Upload className="size-3.5" />
                    Upload WAV
                    <input type="file" accept="audio/*" className="visually-hidden" onChange={handleFileUpload("consent")} />
                  </label>
                </div>
              </div>
            </div>

            {/* Standalone circular HAL 9000 voice meter (zero background box) */}
            <HalVoiceMeter
              telemetry={liveTelemetry}
              recording={recTarget !== null}
              testingMic={testingMic}
              onToggleTestMic={handleToggleTestMic}
            />

            <div className="flex flex-wrap items-center justify-between gap-3 pt-1">
              <p className="text-xs text-zinc-500">
                Requires both the reference calibration sample (minimum 20s of clear speech) and the verbal consent statement without background echo.
              </p>
              <Button
                type="submit"
                variant="primary"
                busy={busy === "create-voice"}
                disabled={!s.keys.length || !voiceName.trim() || !consentClip || !sampleClip || recTarget !== null}
                icon={<Plus className="size-4" />}
              >
                Create &amp; Save Custom Voice
              </Button>
            </div>
          </form>
        ) : (
          <form onSubmit={handlePairExisting} className="space-y-4">
            {keyId ? (
              <VoicePicker
                keyId={keyId}
                value={pickedVoice?.id ?? ""}
                onPick={(v) => {
                  setPickedVoice(v);
                  if (!voiceName.trim()) setVoiceName(v.name);
                }}
              />
            ) : (
              <Alert tone="blue">Add an AI Studio key in the Auth tab first to browse its voices.</Alert>
            )}

            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="When to use this voice">
                <input
                  className="input"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Optional description for agents"
                />
              </Field>
              <Field label="Delivery style">
                <input className="input" value={pairStyle} onChange={(e) => setPairStyle(e.target.value)} />
              </Field>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-3">
              {pickedVoice && (
                <PacingControl
                  value={pairSpeed}
                  onChange={setPairSpeed}
                  with={{ key_id: keyId, voice: pickedVoice.id, style: pairStyle }}
                />
              )}
              <Button
                type="submit"
                variant="primary"
                className="ml-auto"
                busy={busy === "pair-voice"}
                disabled={!keyId || !pickedVoice}
                icon={<Plus className="size-4" />}
              >
                Save Paired Voice
              </Button>
            </div>
          </form>
        )}
      </section>

      <ConfirmDialog
        open={Boolean(deleteTarget)}
        title="Delete voice profile"
        body={`Remove "${deleteTarget?.name || ""}" from Voice Demo Studio? Existing rendered MP4 files remain on disk.`}
        checkboxLabel={
          deleteTarget?.isCustom
            ? "Also delete this custom voice clone from the linked AI Studio project"
            : undefined
        }
        confirmLabel="Delete Voice"
        busy={busy === "delete-voice"}
        onCancel={() => setDeleteTarget(null)}
        onConfirm={(deleteRemote) => {
          if (!deleteTarget) return;
          const id = deleteTarget.id;
          run("delete-voice", async () => {
            updateSettings(await api.deleteProfile(id, deleteRemote));
            setDeleteTarget(null);
            setMsg({ tone: "blue", text: "Voice deleted." });
          });
        }}
      />
    </div>
  );
}

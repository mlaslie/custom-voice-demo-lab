import { ArrowDown, ArrowUp, CheckCircle2, Circle, LayoutTemplate, MousePointerClick, PenLine, Plus, Presentation, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { api, newSegment, slideUrl, speakSeconds, type Project, type Segment, type SegType } from "../../api";
import { VoiceButton } from "../../components/hooks";
import { Alert, Badge, Button, Empty, Field } from "../../components/ui";
import type { TabProps } from "../Project";

const TYPE_META: Record<SegType, { label: string; tone: "blue" | "violet" | "amber"; icon: typeof Presentation }> = {
  card: { label: "Title card", tone: "violet", icon: LayoutTemplate },
  slide: { label: "Slide", tone: "blue", icon: Presentation },
  step: { label: "Web step", tone: "amber", icon: MousePointerClick },
};

const fmt = (s: number) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`;

export default function ScriptTab({ project: p, setProject, goto }: TabProps) {
  const [segs, setSegs] = useState<Segment[]>(p.segments);
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => setSegs(p.segments), [p.segments]);

  const guard = async (fn: () => Promise<Project>) => {
    setErr("");
    try { setProject(await fn()); } catch (e) { setErr((e as Error).message); }
  };
  const patch = (sid: string, b: Partial<Segment>) => {
    // Blur fires even when nothing changed; an unchanged save would needlessly un-approve the script.
    const saved = p.segments.find((x) => x.id === sid) as unknown as Record<string, unknown> | undefined;
    if (saved && Object.entries(b).every(([k, v]) => JSON.stringify(saved[k]) === JSON.stringify(v))) return;
    return guard(() => api.patchSegment(p.id, sid, b));
  };
  const putAll = (next: Segment[]) => { setSegs(next); return guard(async () => (await api.putSegments(p.id, next)).project); };
  const move = (i: number, d: number) => {
    const n = [...segs];
    [n[i], n[i + d]] = [n[i + d], n[i]];
    putAll(n);
  };
  const insert = (i: number, type: SegType) => {
    const n = [...segs];
    n.splice(i + 1, 0, newSegment(type));
    putAll(n);
  };

  if (!segs.length) {
    return (
      <Empty icon={<PenLine className="size-6" />} title="No script yet">
        Your coding agent writes the script from what the session analyzed. It will appear here for you to review,
        edit and approve. You can also start one by hand.
        <div className="mt-4 flex justify-center"><Button onClick={() => insert(-1, "card")}>Start blank</Button></div>
      </Empty>
    );
  }

  const total = segs.reduce((t, s) => t + speakSeconds(s.narration) + speakSeconds(s.after_narration) + (s.type === "card" && !s.narration ? 4 : 1.4), 0);
  const reviewed = segs.filter((s) => s.approved).length;

  return (
    <div className="space-y-4">
      <div className="sticky top-2 z-20 flex flex-wrap items-center gap-3 rounded-2xl border border-zinc-200 bg-white/90 px-4 py-3 shadow-sm backdrop-blur dark:border-zinc-800 dark:bg-zinc-900/90">
        <div className="flex-1 text-sm">
          <span className="font-medium">{segs.length} segments</span>
          <span className="text-zinc-500"> · about {fmt(total)} narrated · {reviewed}/{segs.length} reviewed</span>
        </div>
        {p.script_approved ? (
          <>
            <Badge tone="green"><CheckCircle2 className="size-3" />Approved</Badge>
            <Button size="sm" variant="ghost" onClick={() => guard(() => api.approve(p.id, false))}>Reopen</Button>
            <Button size="sm" variant="primary" onClick={() => goto(p.segments.some((s) => s.type === "step") ? "rehearse" : "render")}>Next</Button>
          </>
        ) : (
          <Button variant="primary" busy={busy} icon={<CheckCircle2 className="size-4" />}
            onClick={async () => { setBusy(true); await guard(() => api.approve(p.id, true)); setBusy(false); }}>
            Approve script
          </Button>
        )}
      </div>
      {err && <Alert>{err}</Alert>}

      {segs.map((s, i) => (
        <SegmentCard key={s.id} p={p} s={s} i={i} last={i === segs.length - 1}
          onLocal={(b) => setSegs(segs.map((x) => (x.id === s.id ? { ...x, ...b } : x)))}
          onSave={(b) => patch(s.id, b)}
          onMove={(d) => move(i, d)}
          onDelete={() => confirm("Delete this segment?") && putAll(segs.filter((x) => x.id !== s.id))}
          onInsert={(t) => insert(i, t)}
        />
      ))}
    </div>
  );
}

function SegmentCard({ p, s, i, last, onLocal, onSave, onMove, onDelete, onInsert }: {
  p: Project; s: Segment; i: number; last: boolean;
  onLocal: (b: Partial<Segment>) => void; onSave: (b: Partial<Segment>) => void;
  onMove: (d: number) => void; onDelete: () => void; onInsert: (t: SegType) => void;
}) {
  const meta = TYPE_META[s.type];
  const [adding, setAdding] = useState(false);

  // Text fields edit locally and save on blur; selects save immediately.
  const text = (k: "title" | "kicker" | "sub" | "narration" | "after_narration" | "notes") => ({
    value: s[k],
    onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => onLocal({ [k]: e.target.value }),
    onBlur: (e: React.FocusEvent<HTMLInputElement | HTMLTextAreaElement>) => onSave({ [k]: e.target.value }),
  });
  const secs = speakSeconds(s.narration) + speakSeconds(s.after_narration);

  return (
    <div className="group/seg">
      <div className={`card overflow-hidden ${s.approved ? "border-emerald-300 dark:border-emerald-900" : ""}`}>
        <div className="flex flex-wrap items-center gap-2 border-b border-zinc-100 px-4 py-2.5 dark:border-zinc-800">
          <span className="w-6 text-xs font-semibold text-zinc-400">{i + 1}</span>
          <Badge tone={meta.tone}><meta.icon className="size-3" />{meta.label}</Badge>
          <select className="rounded-md bg-transparent text-xs text-zinc-500 outline-none" value={s.type}
            onChange={(e) => onSave({ type: e.target.value as SegType, slide: e.target.value === "slide" ? 0 : null })}>
            <option value="card">card</option>
            <option value="slide" disabled={!p.slides.length}>slide</option>
            <option value="step">step</option>
          </select>
          {s.type === "step" && <span className="text-xs text-zinc-500">{s.actions.length} actions</span>}
          <span className="ml-auto text-xs tabular-nums text-zinc-500">~{Math.round(secs)} s</span>
          <div className="flex items-center">
            <Button size="sm" variant="ghost" disabled={i === 0} onClick={() => onMove(-1)} title="Move up"><ArrowUp className="size-3.5" /></Button>
            <Button size="sm" variant="ghost" disabled={last} onClick={() => onMove(1)} title="Move down"><ArrowDown className="size-3.5" /></Button>
            <Button size="sm" variant="ghost" onClick={onDelete} title="Delete"><Trash2 className="size-3.5" /></Button>
          </div>
          <button onClick={() => onSave({ approved: !s.approved })}
            className={`inline-flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-medium ${s.approved ? "text-emerald-700 dark:text-emerald-300" : "text-zinc-500 hover:bg-zinc-100 dark:hover:bg-zinc-800"}`}>
            {s.approved ? <CheckCircle2 className="size-4" /> : <Circle className="size-4" />}{s.approved ? "Reviewed" : "Mark reviewed"}
          </button>
        </div>

        <div className="grid gap-4 p-4 md:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)]">
          <div className="space-y-3">
            {s.type === "card" && (
              <>
                <Field label="Kicker"><input className="input" {...text("kicker")} placeholder="SCENARIO 1" /></Field>
                <Field label="Title"><input className="input font-medium" {...text("title")} /></Field>
                <Field label="Subtitle"><input className="input" {...text("sub")} /></Field>
                <Field label="Bullets (one per line)">
                  <textarea className="input min-h-20" value={s.bullets.join("\n")}
                    onChange={(e) => onLocal({ bullets: e.target.value.split("\n") })}
                    onBlur={(e) => onSave({ bullets: e.target.value.split("\n").map((x) => x.trim()).filter(Boolean) })} />
                </Field>
              </>
            )}
            {s.type === "slide" && (
              <>
                {s.slide !== null && p.slides[s.slide] && (
                  <img src={slideUrl(p.id, s.slide)} alt="" className="aspect-video w-full rounded-lg border border-zinc-200 bg-white object-contain dark:border-zinc-800" />
                )}
                <Field label="Slide">
                  <select className="input" value={s.slide ?? 0} onChange={(e) => onSave({ slide: Number(e.target.value) })}>
                    {p.slides.map((_, n) => <option key={n} value={n}>Slide #{n}</option>)}
                  </select>
                </Field>
              </>
            )}
            {s.type === "step" && (
              <>
                <Field label="Step title"><input className="input font-medium" {...text("title")} /></Field>
                <Field label="What to show (for the action planner)"><textarea className="input min-h-20" {...text("notes")} placeholder="Click the Retail tab, then switch on the PII policy…" /></Field>
                <Field label="Actions run">
                  <select className="input" value={s.actions_at} onChange={(e) => onSave({ actions_at: e.target.value as "during" | "after" })}>
                    <option value="during">While the narration plays</option>
                    <option value="after">After the narration</option>
                  </select>
                </Field>
              </>
            )}
          </div>
          <div className="space-y-3">
            <Field label={s.type === "step" ? "Narration (explain what this step does)" : "Narration"}>
              <textarea className="input min-h-28 text-[15px] leading-relaxed" {...text("narration")} placeholder="What the voice says…" />
            </Field>
            {s.type === "step" && (
              <Field label="After the actions (how the result shows it worked)">
                <textarea className="input min-h-20 text-[15px] leading-relaxed" {...text("after_narration")} />
              </Field>
            )}
            <div className="flex flex-wrap items-center gap-1">
              <VoiceButton text={[s.narration, s.after_narration].filter(Boolean).join(" ")} projectId={p.id} />
              <span className="text-xs text-zinc-400">To rewrite it, ask your coding agent in the chat.</span>
            </div>
          </div>
        </div>
      </div>

      <div className="relative flex h-6 items-center justify-center">
        {adding ? (
          <div className="z-10 flex gap-1 rounded-lg border border-zinc-200 bg-white p-1 shadow-sm dark:border-zinc-700 dark:bg-zinc-900">
            {(["card", "slide", "step"] as SegType[]).map((t) => (
              <Button key={t} size="sm" variant="ghost" disabled={t === "slide" && !p.slides.length} onClick={() => { onInsert(t); setAdding(false); }}>{TYPE_META[t].label}</Button>
            ))}
          </div>
        ) : (
          <button onClick={() => setAdding(true)} className="z-10 rounded-full border border-zinc-200 bg-white p-0.5 text-zinc-400 opacity-0 transition hover:text-brand-600 group-hover/seg:opacity-100 dark:border-zinc-700 dark:bg-zinc-900" title="Insert segment">
            <Plus className="size-3.5" />
          </button>
        )}
      </div>
    </div>
  );
}

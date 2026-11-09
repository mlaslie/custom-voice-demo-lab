import { Loader2 } from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const variants: Record<Variant, string> = {
  primary: "bg-brand-600 text-white hover:bg-brand-700 shadow-sm disabled:bg-brand-600/50",
  secondary:
    "border border-zinc-300 bg-white hover:bg-zinc-50 dark:border-zinc-700 dark:bg-zinc-900 dark:hover:bg-zinc-800",
  ghost: "hover:bg-zinc-100 dark:hover:bg-zinc-800 text-zinc-600 dark:text-zinc-300",
  danger: "text-red-600 hover:bg-red-50 dark:hover:bg-red-950/40",
};

export function Button({
  variant = "secondary", busy, icon, children, className = "", size = "md", ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant; busy?: boolean; icon?: ReactNode; size?: "sm" | "md";
}) {
  const sz = size === "sm" ? "h-8 px-2.5 text-xs gap-1.5" : "h-9 px-3.5 text-sm gap-2";
  return (
    <button
      {...rest}
      disabled={rest.disabled || busy}
      className={`inline-flex shrink-0 items-center justify-center rounded-lg font-medium transition
        disabled:cursor-not-allowed disabled:opacity-60 ${sz} ${variants[variant]} ${className}`}
    >
      {busy ? <Loader2 className="size-4 animate-spin" /> : icon}
      {children}
    </button>
  );
}

export function Badge({ children, tone = "zinc" }: { children: ReactNode; tone?: "zinc" | "blue" | "green" | "amber" | "red" | "violet" }) {
  const t = {
    zinc: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
    blue: "bg-brand-50 text-brand-700 dark:bg-brand-700/25 dark:text-brand-100",
    green: "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300",
    amber: "bg-amber-50 text-amber-800 dark:bg-amber-900/40 dark:text-amber-300",
    red: "bg-red-50 text-red-700 dark:bg-red-900/40 dark:text-red-300",
    violet: "bg-violet-50 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300",
  }[tone];
  return <span className={`inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${t}`}>{children}</span>;
}

export function Field({ label, hint, children, className = "" }: { label: string; hint?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <label className={`block ${className}`}>
      <span className="label">{label}</span>
      {children}
      {hint && <span className="mt-1 block text-xs text-zinc-500">{hint}</span>}
    </label>
  );
}

export function Empty({ icon, title, children }: { icon: ReactNode; title: string; children?: ReactNode }) {
  return (
    <div className="card flex flex-col items-center gap-3 px-6 py-14 text-center">
      <div className="rounded-2xl bg-brand-50 p-3 text-brand-600 dark:bg-brand-700/25 dark:text-brand-100">{icon}</div>
      <h3 className="font-semibold">{title}</h3>
      <div className="max-w-md text-sm text-zinc-500">{children}</div>
    </div>
  );
}

export function Alert({ tone = "red", children }: { tone?: "red" | "amber" | "blue"; children: ReactNode }) {
  const t = {
    red: "border-red-200 bg-red-50 text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200",
    amber: "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200",
    blue: "border-brand-100 bg-brand-50 text-brand-700 dark:border-brand-700/40 dark:bg-brand-700/15 dark:text-brand-100",
  }[tone];
  return <div className={`rounded-xl border px-4 py-3 text-sm ${t}`}>{children}</div>;
}

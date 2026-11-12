import { AlertTriangle, AudioLines, CheckCircle2, FolderKanban, Settings as SettingsIcon, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { api, inAntigravitySidecar, type Settings } from "./api";
import ProjectPage from "./pages/Project";
import Projects from "./pages/Projects";
import SettingsPage from "./pages/Settings";
import Setup from "./pages/Setup";

export default function App() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const loc = useLocation();
  useEffect(() => { api.settings().then(setSettings).catch(() => {}); }, [loc.pathname]);

  // Sync dark mode with Antigravity host theme-change CSS variables or system preference
  useEffect(() => {
    const syncFromHostOrSystem = () => {
      const rootBg = document.documentElement.style.getPropertyValue("--background").trim();
      if (rootBg) {
        const probe = document.createElement("span");
        probe.style.cssText = "position:absolute;visibility:hidden;color:var(--background)";
        document.documentElement.appendChild(probe);
        const computed = getComputedStyle(probe).color;
        probe.remove();
        const nums = (computed.match(/[\d.]+/g) || []).map(Number);
        if (nums.length >= 3) {
          const scale = computed.startsWith("color(") ? 1 : 255;
          const [r, g, b] = nums.slice(0, 3).map((v) => v / scale);
          const lum = 0.2126 * r + 0.7152 * g + 0.0722 * b;
          document.documentElement.classList.toggle("dark", lum < 0.5);
          return;
        }
      }
      const prefersDark = window.matchMedia?.("(prefers-color-scheme: dark)").matches;
      document.documentElement.classList.toggle("dark", Boolean(prefersDark));
    };
    syncFromHostOrSystem();
    const obs = new MutationObserver(syncFromHostOrSystem);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["style"] });
    return () => obs.disconnect();
  }, []);

  const ready = settings && !settings.setup_needed;
  const switchTo = (id: string) => api.activateProfile(id).then(setSettings).catch(() => {});
  const isSidecar = inAntigravitySidecar();

  const nav = ({ isActive }: { isActive: boolean }) =>
    `inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition ${
      isActive ? "bg-brand-50 text-brand-700 dark:bg-brand-700/25 dark:text-brand-100"
        : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"}`;

  return (
    <div className="flex min-h-screen flex-col bg-zinc-50 text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      <header className="sticky top-0 z-30 flex flex-wrap items-center gap-2 border-b border-zinc-200 bg-white/95 px-4 py-2.5 backdrop-blur dark:border-zinc-800 dark:bg-zinc-900/95">
        <Link to="/" className="flex items-center gap-2">
          <span className="grid size-7 place-items-center rounded-lg bg-gradient-to-br from-brand-600 to-emerald-500 text-white shadow-sm">
            <AudioLines className="size-4" />
          </span>
          <span className="text-sm font-semibold tracking-tight">Voice Demo Studio</span>
        </Link>
        {isSidecar && (
          <span className="inline-flex items-center gap-1 rounded-full bg-brand-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-brand-700 dark:bg-brand-700/25 dark:text-brand-100">
            <Sparkles className="size-2.5" /> AGY Plugin
          </span>
        )}

        <nav className="ml-2 flex items-center gap-1">
          <NavLink to="/" end className={nav}><FolderKanban className="size-3.5" />Projects</NavLink>
          <NavLink to="/settings" className={nav}><SettingsIcon className="size-3.5" />Voices</NavLink>
        </nav>

        {settings && (
          <div className="ml-auto flex items-center gap-2 text-xs">
            <span className={`size-2 rounded-full ${ready ? "bg-emerald-500" : "bg-amber-500"}`} />
            {settings.profiles.length > 1 ? (
              <select
                className="rounded-lg border border-zinc-200 bg-zinc-50 px-2 py-1 text-xs font-medium outline-none dark:border-zinc-700 dark:bg-zinc-800"
                value={settings.active_profile}
                onChange={(e) => switchTo(e.target.value)}
                aria-label="Active narrator voice"
              >
                {settings.profiles.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
              </select>
            ) : (
              <Link to={ready ? "/settings" : "/setup"} className="max-w-40 truncate font-medium text-zinc-600 hover:text-brand-600 dark:text-zinc-300">
                {settings.active?.name ?? "Setup voice"}
              </Link>
            )}
            {settings.active && (settings.active.verified_at
              ? <CheckCircle2 className="size-3.5 text-emerald-500" aria-label="Verified" />
              : <AlertTriangle className="size-3.5 text-amber-500" aria-label={settings.active.verify_error || "Not verified"} />)}
          </div>
        )}
      </header>

      <main className="min-w-0 flex-1 px-4 py-5 sm:px-6">
        {settings?.setup_needed && !["/setup", "/settings"].includes(loc.pathname) && <Navigate to="/setup" replace />}
        <Routes>
          <Route path="/setup" element={<Setup settings={settings} onChange={setSettings} />} />
          <Route path="/" element={<Projects settings={settings} />} />
          <Route path="/settings" element={<SettingsPage onChange={setSettings} />} />
          <Route path="/projects/:id" element={<ProjectPage />} />
          <Route path="*" element={<Projects settings={settings} />} />
        </Routes>
      </main>
    </div>
  );
}

import { AudioLines, FolderKanban, KeyRound, Mic, Settings as SettingsIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { api, inAntigravitySidecar, type Settings } from "./api";
import Auth from "./pages/Auth";
import ProjectPage from "./pages/Project";
import Projects from "./pages/Projects";
import SettingsPage from "./pages/Settings";
import VoiceLab from "./pages/VoiceLab";

type TopTabKey = "projects" | "voice-lab" | "auth" | "settings";

const TOP_TABS: { key: TopTabKey; label: string; path: string; icon: typeof FolderKanban }[] = [
  { key: "projects", label: "Projects", path: "/", icon: FolderKanban },
  { key: "voice-lab", label: "Voice Lab", path: "/voice-lab", icon: Mic },
  { key: "auth", label: "Auth", path: "/auth", icon: KeyRound },
  { key: "settings", label: "Settings", path: "/settings", icon: SettingsIcon },
];

export default function App() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const loc = useLocation();
  const navigate = useNavigate();
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  useEffect(() => {
    api.settings().then(setSettings).catch(() => {});
  }, [loc.pathname]);

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

  const ready = Boolean(settings && !settings.setup_needed);
  const isSidecar = inAntigravitySidecar();

  const activeTab: TopTabKey =
    loc.pathname.startsWith("/voice-lab")
      ? "voice-lab"
      : loc.pathname.startsWith("/auth")
        ? "auth"
        : loc.pathname.startsWith("/settings")
          ? "settings"
          : "projects";

  const onTabKeyDown = (idx: number, e: React.KeyboardEvent<HTMLButtonElement>) => {
    let nextIdx = -1;
    if (e.key === "ArrowRight") nextIdx = (idx + 1) % TOP_TABS.length;
    else if (e.key === "ArrowLeft") nextIdx = (idx - 1 + TOP_TABS.length) % TOP_TABS.length;
    else if (e.key === "Home") nextIdx = 0;
    else if (e.key === "End") nextIdx = TOP_TABS.length - 1;
    if (nextIdx !== -1) {
      e.preventDefault();
      navigate(TOP_TABS[nextIdx].path);
      tabRefs.current[nextIdx]?.focus();
    }
  };

  return (
    <div className="flex min-h-screen flex-col bg-zinc-50 text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100">
      <header className="sticky top-0 z-30 border-b border-zinc-200 bg-white/95 px-4 pt-3 backdrop-blur dark:border-zinc-800 dark:bg-zinc-900/95">
        <div className="flex flex-wrap items-center justify-between gap-3 pb-2.5">
          <Link to="/" className="flex items-center gap-2.5">
            <span className="grid size-8 place-items-center rounded-lg bg-brand-600 text-white shadow-sm">
              <AudioLines className="size-4" />
            </span>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-semibold tracking-tight">Voice Demo Studio</span>
                {isSidecar && (
                  <span className="rounded-full bg-brand-50 px-2 py-0.5 text-xs font-medium text-brand-700 dark:bg-brand-700/25 dark:text-brand-100">
                    AGY Sidecar
                  </span>
                )}
              </div>
              <p className="text-xs text-zinc-500 dark:text-zinc-400">
                Active default voice:{" "}
                <span className="font-medium text-zinc-900 dark:text-zinc-100">
                  {settings?.active?.name ?? "None selected"}
                </span>
              </p>
            </div>
          </Link>

          {settings && (
            <Link
              to={ready ? "/voice-lab" : "/auth"}
              className="inline-flex items-center gap-1.5 rounded-full border border-zinc-200 bg-zinc-50 px-2.5 py-1 text-xs font-medium hover:bg-zinc-100 dark:border-zinc-700 dark:bg-zinc-950 dark:hover:bg-zinc-800"
            >
              <span className={`size-2 rounded-full ${ready ? "bg-emerald-500" : "bg-amber-500"}`} />
              <span>{ready ? "AI Studio Ready" : "Setup Needed"}</span>
            </Link>
          )}
        </div>

        <div
          role="tablist"
          aria-label="Voice Demo Studio sections"
          className="studio-tablist"
        >
          {TOP_TABS.map((t, idx) => {
            const Icon = t.icon;
            const selected = activeTab === t.key;
            return (
              <button
                key={t.key}
                ref={(el) => {
                  tabRefs.current[idx] = el;
                }}
                type="button"
                role="tab"
                aria-selected={selected}
                tabIndex={selected ? 0 : -1}
                onClick={() => navigate(t.path)}
                onKeyDown={(e) => onTabKeyDown(idx, e)}
                className="studio-tab"
              >
                <Icon className="size-3.5" aria-hidden="true" />
                <span>{t.label}</span>
              </button>
            );
          })}
        </div>
      </header>

      <main className="min-w-0 flex-1 px-4 py-5 sm:px-6">
        <Routes>
          <Route path="/" element={<Projects settings={settings} />} />
          <Route path="/voice-lab" element={<VoiceLab settings={settings} onChange={setSettings} />} />
          <Route path="/auth" element={<Auth settings={settings} onChange={setSettings} />} />
          <Route path="/settings" element={<SettingsPage onChange={setSettings} />} />
          <Route
            path="/setup"
            element={<Navigate to={settings && !settings.keys.length ? "/auth" : "/voice-lab"} replace />}
          />
          <Route path="/projects/:id" element={<ProjectPage />} />
          <Route path="*" element={<Projects settings={settings} />} />
        </Routes>
      </main>
    </div>
  );
}

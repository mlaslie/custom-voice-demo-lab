import { AudioLines, FolderKanban, Settings as SettingsIcon } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { api, type Settings } from "./api";
import ProjectPage from "./pages/Project";
import Projects from "./pages/Projects";
import SettingsPage from "./pages/Settings";
import Setup from "./pages/Setup";

export default function App() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const loc = useLocation();
  useEffect(() => { api.settings().then(setSettings).catch(() => {}); }, [loc.pathname]);
  const ready = settings && !settings.setup_needed;
  const switchTo = (id: string) => api.activateProfile(id).then(setSettings).catch(() => {});

  const nav = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition ${
      isActive ? "bg-brand-50 text-brand-700 dark:bg-brand-700/25 dark:text-brand-100"
        : "text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-800"}`;

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="flex shrink-0 flex-row items-center gap-2 border-b border-zinc-200 bg-white px-4 py-3 md:sticky md:top-0 md:h-screen md:w-60 md:flex-col md:items-stretch md:border-r md:border-b-0 md:p-4 dark:border-zinc-800 dark:bg-zinc-900">
        <Link to="/" className="flex items-center gap-2.5 md:mb-6 md:px-2">
          <span className="grid size-8 place-items-center rounded-xl bg-gradient-to-br from-brand-500 to-violet-500 text-white shadow-sm">
            <AudioLines className="size-4.5" />
          </span>
          <span className="font-semibold tracking-tight">Voice Demo Lab</span>
        </Link>
        <nav className="ml-auto flex gap-1 md:ml-0 md:flex-col">
          <NavLink to="/" end className={nav}><FolderKanban className="size-4" /><span className="hidden sm:inline">Projects</span></NavLink>
          <NavLink to="/settings" className={nav}><SettingsIcon className="size-4" /><span className="hidden sm:inline">Settings</span></NavLink>
        </nav>
        {settings && (
          <div className="hidden md:mt-auto md:block">
            <div className="rounded-xl border border-zinc-200 p-3 text-xs dark:border-zinc-800">
              <div className="mb-1.5 flex items-center gap-1.5 font-medium">
                <span className={`size-2 rounded-full ${ready ? "bg-emerald-500" : "bg-amber-500"}`} />
                {ready ? "Narrator voice" : "Setup needed"}
              </div>
              {settings.profiles.length > 1 ? (
                <select className="input py-1 text-xs" value={settings.active_profile} onChange={(e) => switchTo(e.target.value)} aria-label="Active voice">
                  {settings.profiles.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
                </select>
              ) : (
                <Link to={ready ? "/settings" : "/setup"} className="block truncate text-zinc-500 hover:text-brand-600">{settings.active?.name ?? "Add a key and a voice"}</Link>
              )}
              {settings.fake_gemini && <div className="mt-1 font-medium text-violet-600">Test mode (no Gemini calls)</div>}
            </div>
          </div>
        )}
      </aside>
      <main className="min-w-0 flex-1 px-4 py-6 md:px-10 md:py-8">
        {settings?.setup_needed && !["/setup", "/settings"].includes(loc.pathname) && <Navigate to="/setup" replace />}
        <Routes>
          <Route path="/setup" element={<Setup settings={settings} onChange={setSettings} />} />
          <Route path="/" element={<Projects settings={settings} />} />
          <Route path="/settings" element={<SettingsPage onChange={setSettings} />} />
          <Route path="/projects/:id" element={<ProjectPage />} />
        </Routes>
      </main>
    </div>
  );
}

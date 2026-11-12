import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, HashRouter } from "react-router-dom";
import App from "./App";
import { inAntigravitySidecar } from "./api";
import "./index.css";

const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
const apply = () => document.documentElement.classList.toggle("dark", Boolean(mq?.matches));
apply();
mq?.addEventListener?.("change", apply);

class RootErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null };
  static getDerivedStateFromError(error: Error) {
    return { error };
  }
  render() {
    if (this.state.error) {
      return (
        <div className="flex min-h-screen flex-col items-center justify-center gap-3 p-6 text-center text-xs">
          <div className="text-sm font-semibold">Voice Demo Studio encountered an error</div>
          <pre className="max-w-md overflow-auto rounded-lg border border-zinc-200 bg-zinc-100 p-3 text-left dark:border-zinc-800 dark:bg-zinc-900">
            {this.state.error.message}
          </pre>
          <button
            onClick={() => window.location.reload()}
            className="rounded-lg bg-brand-600 px-3 py-1.5 font-medium text-white"
          >
            Reload Studio
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

const Router = inAntigravitySidecar() ? HashRouter : BrowserRouter;

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <RootErrorBoundary>
      <Router>
        <App />
      </Router>
    </RootErrorBoundary>
  </React.StrictMode>,
);

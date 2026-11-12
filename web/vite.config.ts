import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

/**
 * Antigravity Sidecar compatibility: emit classic `<script defer>` and `<link rel="stylesheet">`
 * tags without `crossorigin` or `type="module"` so per-sidecar gateway auth cookies and
 * sandboxed webviews never block static asset loads.
 */
function sidecarHtmlCompat(): Plugin {
  return {
    name: "sidecar-html-compat",
    enforce: "post",
    transformIndexHtml(html) {
      return html
        .replace(/<script\s+type="module"\s+crossorigin\s+src="([^"]+)"><\/script>/g, '<script defer src="$1"></script>')
        .replace(/<link\s+rel="stylesheet"\s+crossorigin\s+href="([^"]+)">/g, '<link rel="stylesheet" href="$1">');
    },
  };
}

export default defineConfig({
  plugins: [react(), tailwindcss(), sidecarHtmlCompat()],
  build: {
    outDir: "../demolab/static",
    emptyOutDir: true,
    rollupOptions: {
      output: {
        format: "iife",
        inlineDynamicImports: true,
      },
    },
  },
  server: { port: 5173, proxy: { "/api": "http://127.0.0.1:8765" } },
});

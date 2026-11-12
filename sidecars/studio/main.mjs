/**
 * Google Antigravity Sidecar host for Voice Demo Studio.
 *
 * Bridges Antigravity's Sidecar SDK (`window.sidecar`, `/preload.js`, `/_sidecar/*`,
 * `X-Sidecar-Token` verification) with the local Python `demolab` service (`launch.sh ensure`),
 * serving static Studio assets directly from disk (0ms cold latency) and streaming binary/Range
 * responses for Gemini TTS WAV previews and rendered 1080p MP4s.
 */

import { execFile } from 'node:child_process';
import { existsSync, readFileSync, realpathSync, statSync } from 'node:fs';
import { createServer, get as httpGet, request as httpRequest } from 'node:http';
import { homedir } from 'node:os';
import { dirname, extname, join, sep } from 'node:path';
import { fileURLToPath } from 'node:url';
import { SidecarApp } from 'sidecar_sdk';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PLUGIN_ROOT = join(__dirname, '..', '..');
const STATIC_DIR = join(PLUGIN_ROOT, 'demolab', 'static');
const STATIC_INDEX = join(STATIC_DIR, 'index.html');
const LAUNCH_SH = join(PLUGIN_ROOT, 'scripts', 'launch.sh');
const DEMOLAB_HOME = process.env.DEMOLAB_HOME || join(homedir(), '.demolab');
const PORT_FILE = join(DEMOLAB_HOME, 'port');

const MIME_TYPES = {
  '.js': 'application/javascript; charset=utf-8',
  '.mjs': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.webp': 'image/webp',
  '.woff2': 'font/woff2',
};

const sdkDir = dirname(fileURLToPath(import.meta.resolve('sidecar_sdk')));
const preloadPath = existsSync(join(sdkDir, 'preload.js'))
  ? join(sdkDir, 'preload.js')
  : join(sdkDir, '..', 'preload.js');
const PRELOAD_JS = readFileSync(preloadPath, 'utf-8');

const app = new SidecarApp();
const WEB_PORT = parseInt(process.env.ANTIGRAVITY_SIDECAR_WEB_PORT || '0', 10);
const UI_TOKEN = process.env.ANTIGRAVITY_SIDECAR_UI_TOKEN || '';

let cachedBackend = null; // { hostname, port }
let inflightEnsure = null; // Promise<{ hostname, port }>

function probeHealth(port) {
  return new Promise((resolve) => {
    if (!port || port <= 0) return resolve(false);
    const req = httpGet(
      { hostname: '127.0.0.1', port, path: '/api/health', timeout: 800 },
      (res) => {
        let raw = '';
        res.on('data', (c) => { raw += c; });
        res.on('end', () => {
          try {
            resolve(res.statusCode === 200 && JSON.parse(raw)?.app === 'demolab');
          } catch {
            resolve(false);
          }
        });
      }
    );
    req.on('timeout', () => { req.destroy(); resolve(false); });
    req.on('error', () => resolve(false));
  });
}

async function discoverRunningBackend() {
  const candidates = [];
  if (process.env.DEMOLAB_PORT) {
    candidates.push(parseInt(process.env.DEMOLAB_PORT, 10));
  }
  try {
    const saved = parseInt(readFileSync(PORT_FILE, 'utf-8').trim(), 10);
    if (saved && !candidates.includes(saved)) candidates.push(saved);
  } catch {
    // port file may not exist yet
  }
  if (!candidates.includes(8765)) candidates.push(8765);

  for (const port of candidates) {
    if (await probeHealth(port)) {
      return { hostname: '127.0.0.1', port };
    }
  }
  return null;
}

function spawnEnsureBackend() {
  return new Promise((resolve, reject) => {
    execFile(
      '/bin/sh',
      [LAUNCH_SH, 'ensure'],
      { encoding: 'utf-8', env: process.env, timeout: 45_000 },
      (err, stdout, stderr) => {
        if (err) {
          return reject(new Error((stderr || err.message || 'launch.sh ensure failed').trim()));
        }
        try {
          const lastLine = String(stdout || '').trim().split('\n').pop().trim();
          const parsed = new URL(lastLine);
          resolve({
            hostname: parsed.hostname || '127.0.0.1',
            port: parseInt(parsed.port || '8765', 10),
          });
        } catch (parseErr) {
          reject(new Error(`Invalid backend URL from launch.sh: ${parseErr.message}`));
        }
      }
    );
  });
}

async function ensureBackend(force = false) {
  if (cachedBackend && !force) return cachedBackend;
  if (inflightEnsure) return inflightEnsure;

  inflightEnsure = (async () => {
    try {
      const existing = await discoverRunningBackend();
      if (existing) {
        cachedBackend = existing;
        return existing;
      }
      const started = await spawnEnsureBackend();
      cachedBackend = started;
      return started;
    } finally {
      inflightEnsure = null;
    }
  })();

  return inflightEnsure;
}

function validToken(req, url) {
  if (url.pathname === '/preload.js') return true;
  if (!UI_TOKEN) return true;
  const provided = req.headers['x-sidecar-token'] || url.searchParams.get('token');
  return provided === UI_TOKEN;
}

function readJsonBody(req) {
  return new Promise((resolve, reject) => {
    let raw = '';
    req.on('data', (chunk) => {
      raw += chunk;
    });
    req.on('end', () => {
      try {
        resolve(raw ? JSON.parse(raw) : {});
      } catch (err) {
        reject(err);
      }
    });
    req.on('error', reject);
  });
}

function serveStaticAsset(pathname, res) {
  try {
    if (!existsSync(STATIC_DIR)) return false;
    const rootReal = realpathSync(STATIC_DIR);
    const candidate = join(rootReal, decodeURIComponent(pathname));
    if (!existsSync(candidate)) return false;
    const real = realpathSync(candidate);
    const prefix = rootReal.endsWith(sep) ? rootReal : rootReal + sep;
    if (!real.startsWith(prefix) || !statSync(real).isFile()) return false;

    const ext = extname(real).toLowerCase();
    const contentType = MIME_TYPES[ext] || 'application/octet-stream';
    const body = readFileSync(real);
    res.writeHead(200, {
      'Content-Type': contentType,
      'Content-Length': body.length,
      'Cache-Control': pathname.startsWith('/assets/') ? 'public, max-age=31536000, immutable' : 'no-cache',
    });
    res.end(body);
    return true;
  } catch {
    return false;
  }
}

function serveSpaIndex(res, url) {
  if (!existsSync(STATIC_INDEX)) {
    res.writeHead(503, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end('Voice Demo Studio static bundle is missing (demolab/static/index.html).');
    return;
  }
  let html = readFileSync(STATIC_INDEX, 'utf-8');
  const reqToken = url.searchParams.get('token') || '';
  if (!html.includes('/preload.js')) {
    html = html.replace('<head>', '<head>\n    <script src="/preload.js"></script>');
  }
  if (reqToken) {
    const suffix = `?token=${encodeURIComponent(reqToken)}`;
    html = html
      .replace(/(src="\/assets\/[^"?]+)"/g, `$1${suffix}"`)
      .replace(/(href="\/assets\/[^"?]+)"/g, `$1${suffix}"`);
  }
  const buf = Buffer.from(html, 'utf-8');
  res.writeHead(200, {
    'Content-Type': 'text/html; charset=utf-8',
    'Content-Length': buf.length,
    'Cache-Control': 'no-cache',
  });
  res.end(buf);
}

async function proxyToBackend(req, res, url, retried = false) {
  let target;
  try {
    target = await ensureBackend(retried);
  } catch (err) {
    console.error(`[voice-demo-studio] backend start failed: ${err.message}`);
    res.writeHead(502, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ detail: `Failed to start Voice Demo Lab backend: ${err.message}` }));
    return;
  }

  // Strip sidecar query params (`token`, `conversationId`) before forwarding to FastAPI
  const cleanSearch = new URLSearchParams(url.searchParams);
  cleanSearch.delete('token');
  cleanSearch.delete('conversationId');
  const qs = cleanSearch.toString();
  const forwardPath = url.pathname + (qs ? `?${qs}` : '');

  const fwdHeaders = { ...req.headers };
  fwdHeaders.host = `${target.hostname}:${target.port}`;
  delete fwdHeaders.origin;
  delete fwdHeaders['x-sidecar-token'];
  delete fwdHeaders.connection;

  const upstream = httpRequest(
    {
      hostname: target.hostname,
      port: target.port,
      path: forwardPath,
      method: req.method,
      headers: fwdHeaders,
    },
    (upRes) => {
      const outHeaders = { ...upRes.headers };
      delete outHeaders.connection;
      delete outHeaders['keep-alive'];
      res.writeHead(upRes.statusCode || 200, outHeaders);
      upRes.pipe(res);
    }
  );

  upstream.on('error', (err) => {
    cachedBackend = null;
    if (!retried && (req.method === 'GET' || req.method === 'HEAD')) {
      proxyToBackend(req, res, url, true);
      return;
    }
    console.error(`[voice-demo-studio] proxy error on ${url.pathname}: ${err.message}`);
    if (!res.headersSent) {
      res.writeHead(502, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ detail: `Backend proxy error: ${err.message}` }));
    } else {
      res.end();
    }
  });

  req.pipe(upstream);
}

const server = createServer(async (req, res) => {
  const url = new URL(req.url || '/', `http://127.0.0.1:${WEB_PORT}`);

  if (req.method !== 'GET' && req.method !== 'HEAD' && req.method !== 'OPTIONS' && !validToken(req, url)) {
    res.writeHead(401, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'unauthorized' }));
    return;
  }

  if (req.method === 'GET' && url.pathname === '/preload.js') {
    const buf = Buffer.from(PRELOAD_JS, 'utf-8');
    res.writeHead(200, {
      'Content-Type': 'application/javascript; charset=utf-8',
      'Content-Length': buf.length,
      'Cache-Control': 'no-cache',
    });
    res.end(buf);
    return;
  }

  if (req.method === 'POST' && url.pathname.startsWith('/_sidecar/')) {
    try {
      const data = await readJsonBody(req);
      let out;
      if (url.pathname === '/_sidecar/send-message') {
        out = app.sendMessage(data.conversationId, data.message, {
          title: data.title,
          projectId: data.projectId,
        });
      } else if (url.pathname === '/_sidecar/new-conversation') {
        out = app.startConversation(data.message, {
          model: data.model,
          projectId: data.projectId,
        });
      } else if (url.pathname === '/_sidecar/get-conversation-metadata') {
        out = app.getConversationMetadata(data.conversationId);
      } else {
        res.writeHead(404, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ error: 'Not found' }));
        return;
      }
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(out));
    } catch (err) {
      console.error(`[voice-demo-studio] sidecar API error (${url.pathname}): ${err.message}`);
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: err.message }));
    }
    return;
  }

  if ((req.method === 'GET' || req.method === 'HEAD') && url.pathname.startsWith('/assets/')) {
    if (serveStaticAsset(url.pathname, res)) return;
  }

  if (url.pathname.startsWith('/api/')) {
    await proxyToBackend(req, res, url);
    return;
  }

  if (req.method === 'GET' || req.method === 'HEAD') {
    serveSpaIndex(res, url);
    return;
  }

  res.writeHead(404, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify({ error: 'Not found' }));
});

server.listen(WEB_PORT, '127.0.0.1', () => {
  console.log(`[voice-demo-studio] listening on 127.0.0.1:${server.address().port}`);
  // Warm the Python backend non-blockingly in the background
  ensureBackend(false).catch((err) => {
    console.error('[voice-demo-studio] initial backend warm warning:', err.message);
  });
});

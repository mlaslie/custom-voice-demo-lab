/**
 * Google Antigravity Sidecar host for Voice Demo Studio.
 *
 * Bridges Antigravity's Sidecar SDK (`window.sidecar`, `/preload.js`, `/_sidecar/*`,
 * `X-Sidecar-Token` verification) with the local Python `demolab` service (`launch.sh ensure`),
 * including full binary/Range streaming for Gemini TTS WAV previews and rendered 1080p MP4s.
 */

import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync } from 'node:fs';
import { createServer, request as httpRequest } from 'node:http';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { SidecarApp } from 'sidecar_sdk';

const __dirname = dirname(fileURLToPath(import.meta.url));
const PLUGIN_ROOT = join(__dirname, '..', '..');
const STATIC_INDEX = join(PLUGIN_ROOT, 'demolab', 'static', 'index.html');
const LAUNCH_SH = join(PLUGIN_ROOT, 'scripts', 'launch.sh');

const sdkDir = dirname(fileURLToPath(import.meta.resolve('sidecar_sdk')));
const preloadPath = existsSync(join(sdkDir, 'preload.js'))
  ? join(sdkDir, 'preload.js')
  : join(sdkDir, '..', 'preload.js');
const PRELOAD_JS = readFileSync(preloadPath, 'utf-8');

const app = new SidecarApp();
const WEB_PORT = parseInt(process.env.ANTIGRAVITY_SIDECAR_WEB_PORT || '0', 10);
const UI_TOKEN = process.env.ANTIGRAVITY_SIDECAR_UI_TOKEN || '';

let cachedBackend = null; // { hostname, port }

function ensureBackend(force = false) {
  if (cachedBackend && !force) return cachedBackend;
  const out = execFileSync('/bin/sh', [LAUNCH_SH, 'ensure'], {
    encoding: 'utf-8',
    env: process.env,
    timeout: 45_000,
  }).trim();
  const parsed = new URL(out.split('\n').pop().trim());
  cachedBackend = {
    hostname: parsed.hostname || '127.0.0.1',
    port: parseInt(parsed.port || '8765', 10),
  };
  return cachedBackend;
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

function serveSpaIndex(res) {
  if (!existsSync(STATIC_INDEX)) {
    res.writeHead(503, { 'Content-Type': 'text/plain; charset=utf-8' });
    res.end('Voice Demo Studio static bundle is missing (demolab/static/index.html).');
    return;
  }
  let html = readFileSync(STATIC_INDEX, 'utf-8');
  if (!html.includes('/preload.js')) {
    html = html.replace('<head>', '<head>\n    <script src="/preload.js"></script>');
  }
  res.writeHead(200, {
    'Content-Type': 'text/html; charset=utf-8',
    'Cache-Control': 'no-cache',
  });
  res.end(html);
}

function proxyToBackend(req, res, url, retried = false) {
  let target;
  try {
    target = ensureBackend(retried);
  } catch (err) {
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

  const upstream = httpRequest(
    {
      hostname: target.hostname,
      port: target.port,
      path: forwardPath,
      method: req.method,
      headers: fwdHeaders,
    },
    (upRes) => {
      res.writeHead(upRes.statusCode || 200, upRes.headers);
      upRes.pipe(res);
    }
  );

  upstream.on('error', (err) => {
    if (!retried && (req.method === 'GET' || req.method === 'HEAD')) {
      proxyToBackend(req, res, url, true);
      return;
    }
    cachedBackend = null;
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
    res.writeHead(200, { 'Content-Type': 'application/javascript; charset=utf-8' });
    res.end(PRELOAD_JS);
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
      res.writeHead(500, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: err.message }));
    }
    return;
  }

  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/assets/')) {
    proxyToBackend(req, res, url);
    return;
  }

  if (req.method === 'GET' || req.method === 'HEAD') {
    serveSpaIndex(res);
    return;
  }

  res.writeHead(404, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify({ error: 'Not found' }));
});

server.listen(WEB_PORT, '127.0.0.1', () => {
  console.log(`[voice-demo-studio] listening on 127.0.0.1:${server.address().port}`);
  // Warm the Python backend asynchronously so the first API call is instant
  setTimeout(() => {
    try {
      ensureBackend(false);
    } catch (err) {
      console.error('[voice-demo-studio] initial backend warm warning:', err.message);
    }
  }, 50);
});

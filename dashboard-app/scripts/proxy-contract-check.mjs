import { readFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptsDir = dirname(fileURLToPath(import.meta.url));
const dashboardDir = resolve(scriptsDir, '..');
const proxy = await readFile(
  resolve(dashboardDir, 'projects/dashboard/proxy.conf.js'),
  'utf8',
);
const nginx = await readFile(resolve(dashboardDir, 'nginx.conf.template'), 'utf8');

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

assert(
  proxy.includes("if (req.url?.startsWith('/api/internal/')) return false;"),
  'Vite must bypass /api/internal/ requests',
);
assert(proxy.includes("pathRewrite: { '^/api': '' }"), 'Vite must preserve public /api proxying');
const internalLocation = nginx.indexOf('location ^~ /api/internal/');
const publicLocation = nginx.indexOf('location /api/');
assert(internalLocation >= 0, 'Nginx must deny /api/internal/');
assert(publicLocation >= 0, 'Nginx must preserve public /api/ proxying');
assert(internalLocation < publicLocation, 'Nginx internal denial must precede public proxy');
assert(nginx.indexOf('return 404;', internalLocation) < publicLocation, 'Nginx denial must return 404');

const baseUrl = process.env.SMOKE_BASE_URL || 'http://127.0.0.1:3000';
try {
  const response = await fetch(`${baseUrl}/api/internal/discover/hermes`);
  assert(response.status === 404, `${baseUrl}/api/internal/ returned HTTP ${response.status}`);
  const body = await response.text();
  assert(!body.includes('presented_media_ids'), 'Port 3000 must not expose the internal snapshot');
  assert(!body.includes('required_retain'), 'Port 3000 must not expose generation context');
} catch (error) {
  if (process.env.PROXY_CONTRACT_SKIP_LIVE === '1') {
    console.warn(`proxy-contract-check: live check skipped (${error.message})`);
  } else {
    throw error;
  }
}

console.log('proxy-contract-check: ok');

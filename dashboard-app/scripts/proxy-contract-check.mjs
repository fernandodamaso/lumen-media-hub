import { readFile } from 'node:fs/promises';
import { createRequire } from 'node:module';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const scriptsDir = dirname(fileURLToPath(import.meta.url));
const dashboardDir = resolve(scriptsDir, '..');
const require = createRequire(import.meta.url);
const proxyConfig = require(
  resolve(dashboardDir, 'projects/dashboard/proxy.conf.js'),
);
const proxy = await readFile(
  resolve(dashboardDir, 'projects/dashboard/proxy.conf.js'),
  'utf8',
);
const nginx = await readFile(resolve(dashboardDir, 'nginx.conf.template'), 'utf8');

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const bypass = proxyConfig['/api']?.bypass;
assert(typeof bypass === 'function', 'Vite /api proxy must define bypass(req)');

const privateBrowserPaths = [
  '/api/internal/discover/hermes',
  '/api/discover/hermes/generations',
  '/api/discover/hermes/sync',
];

const publicBrowserPaths = [
  '/api/discover/hermes',
  '/api/discover/hermes/request-more',
  '/api/discover/hermes/hermes-movie-1',
  '/api/discover/request',
];

for (const path of privateBrowserPaths) {
  assert(bypass({ url: path }) === false, `Vite must reject ${path}`);
}

for (const path of publicBrowserPaths) {
  assert(bypass({ url: path }) === undefined, `Vite must proxy ${path}`);
}

assert(
  proxyConfig['/api']?.pathRewrite && proxyConfig['/api'].pathRewrite['^/api'] === '',
  'Vite must preserve public /api proxying',
);
assert(proxy.includes("pathRewrite: { '^/api': '' }"), 'Vite must preserve public /api proxying');
const internalLocation = nginx.indexOf('location ^~ /api/internal/');
const generationLocation = nginx.indexOf(
  'location = /api/discover/hermes/generations',
);
const syncLocation = nginx.indexOf('location = /api/discover/hermes/sync');
const publicLocation = nginx.indexOf('location /api/');
assert(internalLocation >= 0, 'Nginx must deny /api/internal/');
assert(generationLocation >= 0, 'Nginx must deny browser generation POSTs');
assert(syncLocation >= 0, 'Nginx must deny browser Hermes sync POSTs');
assert(publicLocation >= 0, 'Nginx must preserve public /api/ proxying');
assert(internalLocation < publicLocation, 'Nginx internal denial must precede public proxy');
assert(generationLocation < publicLocation, 'Generation denial must precede /api/');
assert(syncLocation < publicLocation, 'Sync denial must precede /api/');
assert(nginx.indexOf('return 404;', internalLocation) < publicLocation, 'Nginx denial must return 404');

const baseUrl = process.env.SMOKE_BASE_URL || 'http://127.0.0.1:3000';
try {
  for (const path of [
    '/api/internal/discover/hermes',
    '/api/discover/hermes/generations',
    '/api/discover/hermes/sync',
  ]) {
    const response = await fetch(`${baseUrl}${path}`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: '{}',
    });
    assert(response.status === 404, `${baseUrl}${path} returned HTTP ${response.status}`);
  }

  const publicResponse = await fetch(`${baseUrl}/api/discover/hermes`);
  assert(publicResponse.status === 200, 'Public Hermes GET must remain proxied');

  const response = await fetch(`${baseUrl}/api/internal/discover/hermes`);
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

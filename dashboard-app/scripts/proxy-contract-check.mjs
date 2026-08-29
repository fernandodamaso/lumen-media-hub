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
  '/api/internal/ai-picks/jobs/claim',
  '/api/internal/ai-picks/jobs/job-1/complete',
  '/api/internal/ai-picks/jobs/job-1/fail',
];

const publicBrowserPaths = [
  '/api/discover/ai-picks',
  '/api/discover/ai-picks/request-more',
  '/api/discover/ai-picks/ai-movie-1',
  '/api/discover/request',
];

for (const path of privateBrowserPaths) {
  assert(bypass({ url: path }) === false, `Vite must reject ${path}`);
}

for (const path of publicBrowserPaths) {
  assert(bypass({ url: path }) === undefined, `Vite must proxy ${path}`);
}

assert(proxy.includes("path.startsWith('/api/library/items/')"), 'Vite must inject token for library delete preview GETs');
assert(
  proxyConfig['/api']?.pathRewrite && proxyConfig['/api'].pathRewrite['^/api'] === '',
  'Vite must preserve public /api proxying',
);
assert(proxy.includes("pathRewrite: { '^/api': '' }"), 'Vite must preserve public /api proxying');
const internalLocation = nginx.indexOf('location ^~ /api/internal/');
const publicLocation = nginx.indexOf('location /api/');
assert(internalLocation >= 0, 'Nginx must deny /api/internal/');
assert(publicLocation >= 0, 'Nginx must preserve public /api/ proxying');
assert(internalLocation < publicLocation, 'Nginx internal denial must precede public proxy');
assert(nginx.indexOf('return 404;', internalLocation) < publicLocation, 'Nginx denial must return 404');

const baseUrl = process.env.SMOKE_BASE_URL || 'http://127.0.0.1:3000';
const liveDenialProbes = [
  { path: '/api/internal/ai-picks/jobs/claim', method: 'GET' },
];
const internalProbe = liveDenialProbes.find(
  (candidate) => candidate.path === '/api/internal/ai-picks/jobs/claim',
);
assert(internalProbe?.method === 'GET', 'Internal AI Picks denial probe must use GET');

try {
  for (const { path, method } of liveDenialProbes) {
    const response = await fetch(`${baseUrl}${path}`, {
      method,
    });
    assert(response.status === 404, `${baseUrl}${path} returned HTTP ${response.status}`);
  }

  const publicResponse = await fetch(`${baseUrl}/api/discover/ai-picks`);
  assert(publicResponse.status === 200, 'Public AI Picks GET must remain proxied');

  const response = await fetch(`${baseUrl}/api/internal/ai-picks/jobs/claim`);
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

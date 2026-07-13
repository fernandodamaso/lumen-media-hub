/**
 * Cross-platform Pages packaging:
 * 1. Production-like pages build with baseHref /media-manager-angular/
 * 2. Copy index.html → 404.html for SPA fallback on static hosts
 * 3. Assert base href + artifact hygiene (no localhost / private links /api)
 */
import { spawnSync } from 'node:child_process';
import { copyFileSync, existsSync, mkdirSync, readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

const root = process.cwd();
const browserDir = join(root, 'dist', 'dashboard', 'browser');
const expectedBaseHref = '/media-manager-angular/';

const forbidden = [
  { label: 'localhost', pattern: /localhost/i },
  { label: '127.0.0.1', pattern: /127\.0\.0\.1/ },
  { label: 'Jellyfin default port', pattern: /:8096\b/ },
  { label: 'Sonarr default port', pattern: /:8989\b/ },
  { label: 'Radarr default port', pattern: /:7878\b/ },
  { label: '/api traffic', pattern: /['"`]\/api(?:\/|['"`])/ },
];

function run(command, args) {
  const result = spawnSync(command, args, {
    cwd: root,
    stdio: 'inherit',
    shell: process.platform === 'win32',
  });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

function collectFiles(dir, acc = []) {
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) {
      collectFiles(full, acc);
    } else if (/\.(html|js|css|txt|json|svg|map)$/i.test(name)) {
      acc.push(full);
    }
  }
  return acc;
}

console.log('Building dashboard (pages configuration)...');
run('npx', ['ng', 'build', 'dashboard', '--configuration=pages']);

if (!existsSync(browserDir)) {
  console.error(`Missing publishable root: ${browserDir}`);
  process.exit(1);
}

const indexPath = join(browserDir, 'index.html');
const notFoundPath = join(browserDir, '404.html');

if (!existsSync(indexPath)) {
  console.error(`Missing ${indexPath}`);
  process.exit(1);
}

mkdirSync(browserDir, { recursive: true });
copyFileSync(indexPath, notFoundPath);

const indexHtml = readFileSync(indexPath, 'utf8');
if (!indexHtml.includes(`href="${expectedBaseHref}"`) && !indexHtml.includes(`href='${expectedBaseHref}'`)) {
  console.error(`index.html base href must be ${expectedBaseHref}`);
  process.exit(1);
}

if (!existsSync(notFoundPath)) {
  console.error(`Failed to create ${notFoundPath}`);
  process.exit(1);
}

const files = collectFiles(browserDir);
const violations = [];

for (const file of files) {
  const text = readFileSync(file, 'utf8');
  for (const rule of forbidden) {
    if (rule.pattern.test(text)) {
      violations.push(`${file.replace(root + '\\', '').replace(root + '/', '')}: ${rule.label}`);
    }
  }
}

if (violations.length) {
  console.error('Pages artifact hygiene failed:');
  for (const v of violations) console.error(`  - ${v}`);
  process.exit(1);
}

console.log(`Pages artifact ready at ${browserDir}`);
console.log(`  - base href: ${expectedBaseHref}`);
console.log('  - 404.html SPA fallback copied');
console.log('  - hygiene scan passed');

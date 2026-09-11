import {
  CleanupBlockCode,
  CleanupCandidate,
  CleanupPreview,
  CleanupReason,
  CleanupRuleCode,
  CleanupUnresolvedItem,
} from './cleanup.models';

const CANDIDATE_ID = /^sg_[0-9a-f]{24}$/;
const PREVIEW_ID = /^sgp_[0-9a-f]{24}$/;
const UNRESOLVED_ID = /^unresolved_[0-9a-f]{20}$/;
const RULE_CODES = new Set<CleanupRuleCode>([
  'watched_movie_expired',
  'watched_episode_expired',
  'large_watched_file_stale',
]);
const BLOCK_CODES = new Set<CleanupBlockCode>([
  'in_progress',
  'never_watched',
  'favorite',
  'manual_pin',
  'recent_addition',
  'no_matching_rule',
]);

export function requireCleanupPreview(value: unknown): CleanupPreview {
  const root = record(value, 'Malformed cleanup preview');
  exactKeys(root, [
    'schemaVersion', 'previewId', 'generatedAt', 'status', 'storage', 'summary',
    'candidates', 'blocked', 'unresolved', 'warnings',
  ], 'cleanup preview');
  if (root['schemaVersion'] !== 1) fail('unsupported schemaVersion');
  const previewId = text(root['previewId'], 'previewId');
  if (!PREVIEW_ID.test(previewId)) fail('invalid previewId');
  const generatedAt = timestamp(root['generatedAt'], 'generatedAt');
  const status = root['status'];
  if (status !== 'complete' && status !== 'degraded') fail('invalid status');

  const storage = requireStorage(root['storage']);
  const summary = requireSummary(root['summary']);
  const candidates = array(root['candidates'], 'candidates').map(requireCandidate);
  const blocked = array(root['blocked'], 'blocked').map(requireBlock);
  const unresolved = array(root['unresolved'], 'unresolved').map(requireUnresolved);
  const warnings = array(root['warnings'], 'warnings').map((entry, index) => text(entry, `warnings[${index}]`, true));

  const ids = new Set(candidates.map((candidate) => candidate.id));
  if (ids.size !== candidates.length) fail('duplicate candidate id');
  const eligibleBytes = candidates.reduce((total, candidate) => total + candidate.sizeBytes, 0);
  const recommended = candidates.filter((candidate) => candidate.recommended);
  const recommendedBytes = recommended.reduce((total, candidate) => total + candidate.sizeBytes, 0);
  if (summary.eligibleFiles !== candidates.length || summary.recommendedFiles !== recommended.length) {
    fail('summary candidate counts are inconsistent');
  }
  if (storage.eligibleBytes !== eligibleBytes || storage.recommendedBytes !== recommendedBytes) {
    fail('storage candidate bytes are inconsistent');
  }
  if (storage.requiredReclaimBytes !== Math.max(0, storage.targetFreeBytes - storage.freeBytes)) {
    fail('required reclaim is inconsistent');
  }
  if (storage.projectedFreeBytes !== Math.min(storage.totalBytes, storage.freeBytes + storage.recommendedBytes)) {
    fail('projected free space is inconsistent');
  }
  if (storage.remainingShortfallBytes !== Math.max(0, storage.targetFreeBytes - storage.projectedFreeBytes)) {
    fail('remaining shortfall is inconsistent');
  }
  if (summary.unresolvedFiles !== unresolved.length) fail('unresolved count is inconsistent');
  if (status === 'complete' && unresolved.length) fail('complete preview cannot contain unresolved items');

  return {
    schemaVersion: 1,
    previewId,
    generatedAt,
    status,
    storage,
    summary,
    candidates,
    blocked,
    unresolved,
    warnings,
  };
}

function requireStorage(value: unknown): CleanupPreview['storage'] {
  const input = record(value, 'Malformed cleanup preview storage');
  const keys = [
    'totalBytes', 'usedBytes', 'freeBytes', 'targetFreeBytes', 'requiredReclaimBytes',
    'eligibleBytes', 'recommendedBytes', 'projectedFreeBytes', 'remainingShortfallBytes',
  ] as const;
  exactKeys(input, [...keys], 'storage');
  const result = Object.fromEntries(keys.map((key) => [key, nonNegativeInteger(input[key], `storage.${key}`)])) as unknown as CleanupPreview['storage'];
  if (result.usedBytes > result.totalBytes || result.freeBytes > result.totalBytes) fail('invalid storage capacity');
  return result;
}

function requireSummary(value: unknown): CleanupPreview['summary'] {
  const input = record(value, 'Malformed cleanup preview summary');
  const keys = ['scannedFiles', 'eligibleFiles', 'recommendedFiles', 'protectedFiles', 'unresolvedFiles'] as const;
  exactKeys(input, [...keys], 'summary');
  return Object.fromEntries(keys.map((key) => [key, nonNegativeInteger(input[key], `summary.${key}`)])) as unknown as CleanupPreview['summary'];
}

function requireCandidate(value: unknown, index: number): CleanupCandidate {
  const input = record(value, `Malformed candidate ${index}`);
  exactKeys(input, [
    'id', 'mediaKind', 'title', 'subtitle', 'href', 'sizeBytes', 'dateAdded',
    'lastPlayedAt', 'recommended', 'reasons',
  ], `candidate ${index}`);
  const id = text(input['id'], `candidate ${index} id`);
  if (!CANDIDATE_ID.test(id)) fail(`candidate ${index} has invalid id`);
  const mediaKind = input['mediaKind'];
  if (mediaKind !== 'movie' && mediaKind !== 'episode') fail(`candidate ${index} has invalid mediaKind`);
  const href = input['href'] === null ? null : safeHref(input['href'], index);
  if (typeof input['recommended'] !== 'boolean') fail(`candidate ${index} has invalid recommended flag`);
  const reasons = array(input['reasons'], `candidate ${index} reasons`).map((reason, reasonIndex) =>
    requireReason(reason, index, reasonIndex),
  );
  if (!reasons.length) fail(`candidate ${index} has no rule evidence`);
  return {
    id,
    mediaKind,
    title: text(input['title'], `candidate ${index} title`),
    subtitle: text(input['subtitle'], `candidate ${index} subtitle`),
    href,
    sizeBytes: positiveInteger(input['sizeBytes'], `candidate ${index} sizeBytes`),
    dateAdded: timestamp(input['dateAdded'], `candidate ${index} dateAdded`),
    lastPlayedAt: timestamp(input['lastPlayedAt'], `candidate ${index} lastPlayedAt`),
    recommended: input['recommended'],
    reasons,
  };
}

function requireReason(value: unknown, candidateIndex: number, reasonIndex: number): CleanupReason {
  const input = record(value, `Malformed candidate ${candidateIndex} reason ${reasonIndex}`);
  exactKeys(input, ['code', 'evidence'], 'cleanup reason');
  const code = input['code'];
  if (typeof code !== 'string' || !RULE_CODES.has(code as CleanupRuleCode)) fail('invalid cleanup reason code');
  const evidence = record(input['evidence'], 'Malformed cleanup reason evidence');
  const expected = code === 'watched_movie_expired'
    ? ['retentionDays']
    : code === 'watched_episode_expired'
      ? ['retentionDays', 'keepLatestPerSeries']
      : ['minimumBytes', 'idleDays'];
  exactKeys(evidence, expected, 'cleanup reason evidence');
  const normalized: Record<string, number> = {};
  for (const key of expected) normalized[key] = nonNegativeInteger(evidence[key], `reason evidence ${key}`);
  return { code: code as CleanupRuleCode, evidence: normalized };
}

function requireBlock(value: unknown, index: number): CleanupPreview['blocked'][number] {
  const input = record(value, `Malformed blocked summary ${index}`);
  exactKeys(input, ['code', 'count', 'bytes'], 'blocked summary');
  const code = input['code'];
  if (typeof code !== 'string' || !BLOCK_CODES.has(code as CleanupBlockCode)) fail('invalid blocked code');
  return {
    code: code as CleanupBlockCode,
    count: nonNegativeInteger(input['count'], 'blocked count'),
    bytes: nonNegativeInteger(input['bytes'], 'blocked bytes'),
  };
}

function requireUnresolved(value: unknown, index: number): CleanupUnresolvedItem {
  const input = record(value, `Malformed unresolved item ${index}`);
  exactKeys(input, ['id', 'title', 'mediaKind', 'reason'], 'unresolved item');
  const id = text(input['id'], 'unresolved id');
  if (!UNRESOLVED_ID.test(id)) fail('invalid unresolved id');
  const mediaKind = input['mediaKind'];
  if (mediaKind !== 'movie' && mediaKind !== 'episode' && mediaKind !== 'unknown') fail('invalid unresolved mediaKind');
  return {
    id,
    title: text(input['title'], 'unresolved title'),
    mediaKind,
    reason: text(input['reason'], 'unresolved reason'),
  };
}

function safeHref(value: unknown, index: number): string {
  const href = text(value, `candidate ${index} href`);
  let parsed: URL;
  try { parsed = new URL(href); } catch { fail(`candidate ${index} has invalid href`); }
  if (parsed!.protocol !== 'http:' && parsed!.protocol !== 'https:') fail(`candidate ${index} has unsafe href`);
  if (parsed!.username || parsed!.password) fail(`candidate ${index} href contains credentials`);
  return href;
}

function record(value: unknown, message: string): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(message);
  return value as Record<string, unknown>;
}

function array(value: unknown, field: string): unknown[] {
  if (!Array.isArray(value)) fail(`${field} must be an array`);
  return value;
}

function exactKeys(value: Record<string, unknown>, keys: string[], field: string): void {
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    fail(`${field} contains unexpected fields`);
  }
}

function text(value: unknown, field: string, allowEmpty = false): string {
  if (typeof value !== 'string') fail(`${field} must be a string`);
  const normalized = value.trim();
  if (!allowEmpty && !normalized) fail(`${field} must not be empty`);
  if (normalized.length > 500) fail(`${field} is too long`);
  return normalized;
}

function timestamp(value: unknown, field: string): string {
  const normalized = text(value, field);
  if (Number.isNaN(Date.parse(normalized))) fail(`${field} is not a timestamp`);
  return normalized;
}

function nonNegativeInteger(value: unknown, field: string): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < 0) fail(`${field} must be a non-negative safe integer`);
  return value;
}

function positiveInteger(value: unknown, field: string): number {
  const normalized = nonNegativeInteger(value, field);
  if (normalized <= 0) fail(`${field} must be positive`);
  return normalized;
}

function fail(detail: string): never {
  throw new Error(`Malformed cleanup preview: ${detail}`);
}

import { Injectable } from '@angular/core';

import {
  CleanupCandidate,
  CleanupPreview,
  CleanupPreviewRequest,
  CleanupReason,
  GIB,
} from '../storage/cleanup.models';
import { MockMediaStackApi } from './mock-media-stack-api';

export type StorageGuardianScenario = 'ready' | 'target-met' | 'insufficient' | 'degraded' | 'error';

@Injectable()
export class StorageGuardianMockMediaStackApi extends MockMediaStackApi {
  private storageGuardianScenario: StorageGuardianScenario = 'ready';

  setStorageGuardianScenario(scenario: StorageGuardianScenario): void {
    this.storageGuardianScenario = scenario;
  }

  async previewStorageCleanup(
    policy: CleanupPreviewRequest,
    signal?: AbortSignal,
  ): Promise<CleanupPreview> {
    if (signal?.aborted) throw abortError();
    if (this.storageGuardianScenario === 'error') {
      await abortable(this.withLatency(undefined), signal);
      throw new Error('Cleanup preview fixture unavailable');
    }
    const preview = buildDemoPreview(policy, this.storageGuardianScenario);
    return abortable(this.withLatency(preview), signal);
  }
}

function buildDemoPreview(policy: CleanupPreviewRequest, scenario: Exclude<StorageGuardianScenario, 'error'>): CleanupPreview {
  const generatedAt = new Date().toISOString();
  const source = demoCandidates(generatedAt).filter((candidate) => {
    if (policy.protections.pinnedCandidateIds.includes(candidate.id)) return false;
    const code = candidate.reasons[0]?.code;
    if (code === 'watched_movie_expired') return policy.rules.watchedMovies.enabled;
    if (code === 'watched_episode_expired') return policy.rules.watchedEpisodes.enabled;
    return policy.rules.largeWatchedFiles.enabled;
  });
  const candidates = scenario === 'insufficient' ? source.slice(0, 3) : source;
  const freeBytes = scenarioFreeBytes(scenario);
  const totalBytes = 4_000 * GIB;
  const requiredReclaimBytes = Math.max(0, policy.targetFreeBytes - freeBytes);
  let recommendedBytes = 0;
  const normalized = candidates.map((candidate) => ({ ...candidate, recommended: false }));
  for (const candidate of normalized) {
    if (recommendedBytes >= requiredReclaimBytes) break;
    if (requiredReclaimBytes > 0) {
      candidate.recommended = true;
      recommendedBytes += candidate.sizeBytes;
    }
  }
  const eligibleBytes = normalized.reduce((total, candidate) => total + candidate.sizeBytes, 0);
  const recommendedFiles = normalized.filter((candidate) => candidate.recommended).length;
  const projectedFreeBytes = Math.min(totalBytes, freeBytes + recommendedBytes);
  const remainingShortfallBytes = Math.max(0, policy.targetFreeBytes - projectedFreeBytes);
  const unresolved = scenario === 'degraded'
    ? [{ id: 'unresolved_11111111111111111111', title: 'Alternate cut', mediaKind: 'movie' as const, reason: 'ambiguous_versions' }]
    : [];
  const warnings = [
    ...(unresolved.length ? ['1 Jellyfin item(s) need review and were excluded from recommendations.'] : []),
    ...(remainingShortfallBytes ? ['Safe candidates cannot currently restore the configured free-space target.'] : []),
  ];

  return {
    schemaVersion: 1,
    previewId: 'sgp_111111111111111111111111',
    generatedAt,
    status: unresolved.length ? 'degraded' : 'complete',
    storage: {
      totalBytes,
      usedBytes: totalBytes - freeBytes,
      freeBytes,
      targetFreeBytes: policy.targetFreeBytes,
      requiredReclaimBytes,
      eligibleBytes,
      recommendedBytes,
      projectedFreeBytes,
      remainingShortfallBytes,
    },
    summary: {
      scannedFiles: normalized.length + unresolved.length + policy.protections.pinnedCandidateIds.length,
      eligibleFiles: normalized.length,
      recommendedFiles,
      protectedFiles: policy.protections.pinnedCandidateIds.length + 4,
      unresolvedFiles: unresolved.length,
    },
    candidates: normalized,
    blocked: policy.protections.pinnedCandidateIds.length
      ? [{ code: 'manual_pin', count: policy.protections.pinnedCandidateIds.length, bytes: 0 }]
      : [],
    unresolved,
    warnings,
  };
}

function scenarioFreeBytes(scenario: Exclude<StorageGuardianScenario, 'error'>): number {
  if (scenario === 'target-met') return 260 * GIB;
  if (scenario === 'insufficient') return 100 * GIB;
  return 118 * GIB;
}

function demoCandidates(generatedAt: string): CleanupCandidate[] {
  return [
    candidate('1', 'movie', 'Dune: Part Two', 'Movie · 2024', 31.2, 120, movieReason(30), generatedAt),
    candidate('2', 'episode', 'The Last of Us', 'Episode · S01E03', 5.4, 105, episodeReason(14, 3), generatedAt),
    candidate('3', 'episode', 'Severance', 'Episode · S01E01', 4.8, 96, episodeReason(14, 3), generatedAt),
    candidate('4', 'movie', 'Arrival', 'Movie · 2016', 12, 88, movieReason(30), generatedAt),
    candidate('5', 'movie', 'Blade Runner 2049', 'Movie · 2017', 10, 79, movieReason(30), generatedAt),
    candidate('6', 'episode', 'Andor', 'Episode · S01E04', 8, 71, episodeReason(14, 3), generatedAt),
    candidate('7', 'movie', 'Moon', 'Movie · 2009', 6.6, 61, largeReason(20 * GIB, 90), generatedAt),
    candidate('8', 'movie', 'Interstellar', 'Movie · 2014', 16, 48, movieReason(30), generatedAt),
  ];
}

function candidate(
  digit: string,
  mediaKind: 'movie' | 'episode',
  title: string,
  subtitle: string,
  gib: number,
  daysAgo: number,
  reason: CleanupReason,
  generatedAt: string,
): CleanupCandidate {
  const now = Date.parse(generatedAt);
  const day = 86_400_000;
  return {
    id: `sg_${digit.repeat(24)}`,
    mediaKind,
    title,
    subtitle,
    href: `http://127.0.0.1:8096/web/index.html#!/details?id=demo-${digit}`,
    sizeBytes: Math.round(gib * GIB),
    dateAdded: new Date(now - (daysAgo + 60) * day).toISOString(),
    lastPlayedAt: new Date(now - daysAgo * day).toISOString(),
    recommended: false,
    reasons: [reason],
  };
}

function movieReason(retentionDays: number): CleanupReason {
  return { code: 'watched_movie_expired', evidence: { retentionDays } };
}

function episodeReason(retentionDays: number, keepLatestPerSeries: number): CleanupReason {
  return { code: 'watched_episode_expired', evidence: { retentionDays, keepLatestPerSeries } };
}

function largeReason(minimumBytes: number, idleDays: number): CleanupReason {
  return { code: 'large_watched_file_stale', evidence: { minimumBytes, idleDays } };
}

async function abortable<T>(promise: Promise<T>, signal?: AbortSignal): Promise<T> {
  if (!signal) return promise;
  if (signal.aborted) throw abortError();
  return Promise.race([
    promise,
    new Promise<T>((_, reject) => {
      signal.addEventListener('abort', () => {
        reject(abortError());
      }, { once: true });
    }),
  ]);
}

function abortError(): DOMException {
  return new DOMException('The operation was aborted.', 'AbortError');
}

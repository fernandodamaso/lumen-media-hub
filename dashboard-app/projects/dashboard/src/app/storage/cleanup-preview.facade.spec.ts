import { TestBed } from '@angular/core/testing';

import { MEDIA_STACK_API, MediaStackApi } from '../media-stack/media-stack-api';
import { CleanupPreview, CleanupPreviewRequest, GIB } from './cleanup.models';
import { CleanupPreviewFacade } from './cleanup-preview.facade';

describe('CleanupPreviewFacade', () => {
  let calls: CleanupPreviewRequest[];
  let responder: (request: CleanupPreviewRequest, signal?: AbortSignal) => Promise<CleanupPreview>;

  beforeEach(() => {
    localStorage.clear();
    calls = [];
    responder = (request) => Promise.resolve(demoPreview(request));
    TestBed.configureTestingModule({
      providers: [
        CleanupPreviewFacade,
        {
          provide: MEDIA_STACK_API,
          useValue: {
            previewStorageCleanup: (request: CleanupPreviewRequest, signal?: AbortSignal) => {
              calls.push(request);
              return responder(request, signal);
            },
          } as unknown as MediaStackApi,
        },
      ],
    });
  });

  it('stays idle until Run preview is explicit', async () => {
    const facade = TestBed.inject(CleanupPreviewFacade);
    expect(facade.phase()).toBe('idle');
    expect(calls.length).toBe(0);

    await facade.runPreview();

    expect(calls.length).toBe(1);
    expect(facade.phase()).toBe('ready');
    expect(facade.preview()?.summary.eligibleFiles).toBe(1);
  });

  it('aborts an older preview when a newer run starts', async () => {
    const facade = TestBed.inject(CleanupPreviewFacade);
    const signals: AbortSignal[] = [];
    responder = (request, signal) => {
      if (signal) signals.push(signal);
      if (signals.length === 1) {
        return new Promise<CleanupPreview>((_resolve, reject) => {
          signal?.addEventListener('abort', () => {
            reject(new DOMException('aborted', 'AbortError'));
          }, { once: true });
        });
      }
      return Promise.resolve(demoPreview(request));
    };

    const first = facade.runPreview();
    await Promise.resolve();
    const second = facade.runPreview();
    await Promise.all([first, second]);

    expect(calls.length).toBe(2);
    expect(signals[0]?.aborted).toBe(true);
    expect(facade.phase()).toBe('ready');
    expect(facade.preview()?.summary.eligibleFiles).toBe(1);
  });

  it('marks the last result stale after policy or pin changes without auto-running', async () => {
    const facade = TestBed.inject(CleanupPreviewFacade);
    await facade.runPreview();
    facade.setMovieRetention('45 days');
    expect(facade.phase()).toBe('stale');
    expect(calls.length).toBe(1);

    facade.keepCandidate('sg_111111111111111111111111');
    expect(facade.phase()).toBe('stale');
    expect(calls.length).toBe(1);
    expect(localStorage.getItem('lumen.storageGuardian.pins.v1')).toContain('sg_111111111111111111111111');
  });

  it('preserves the last successful preview when refresh fails', async () => {
    const facade = TestBed.inject(CleanupPreviewFacade);
    await facade.runPreview();
    const first = facade.preview();
    facade.setMovieRetention('60');
    responder = () => Promise.reject(new Error('temporary fixture error'));

    await facade.runPreview();

    expect(facade.preview()).toBe(first);
    expect(facade.phase()).toBe('stale');
    expect(facade.warning()).toContain('last successful simulation');
  });

  it('resets corrupt persisted state to safe defaults', () => {
    localStorage.setItem('lumen.storageGuardian.policy.v1', '{bad-json');
    localStorage.setItem('lumen.storageGuardian.pins.v1', JSON.stringify({ schemaVersion: 1, ids: ['../../private'] }));

    const facade = TestBed.inject(CleanupPreviewFacade);

    expect(facade.policy().rules.watchedMovies.retentionDays).toBe(30);
    expect(facade.pinnedIds()).toEqual([]);
    expect(localStorage.getItem('lumen.storageGuardian.policy.v1')).toBeNull();
    expect(localStorage.getItem('lumen.storageGuardian.pins.v1')).toBeNull();
  });
});

function demoPreview(request: CleanupPreviewRequest): CleanupPreview {
  const freeBytes = 100 * GIB;
  const sizeBytes = 10 * GIB;
  return {
    schemaVersion: 1,
    previewId: 'sgp_111111111111111111111111',
    generatedAt: '2026-09-11T12:00:00Z',
    status: 'complete',
    storage: {
      totalBytes: 1000 * GIB,
      usedBytes: 900 * GIB,
      freeBytes,
      targetFreeBytes: request.targetFreeBytes,
      requiredReclaimBytes: Math.max(0, request.targetFreeBytes - freeBytes),
      eligibleBytes: sizeBytes,
      recommendedBytes: sizeBytes,
      projectedFreeBytes: freeBytes + sizeBytes,
      remainingShortfallBytes: Math.max(0, request.targetFreeBytes - freeBytes - sizeBytes),
    },
    summary: { scannedFiles: 1, eligibleFiles: 1, recommendedFiles: 1, protectedFiles: 0, unresolvedFiles: 0 },
    candidates: [{
      id: 'sg_111111111111111111111111',
      mediaKind: 'movie',
      title: 'Demo Movie',
      subtitle: 'Movie · 2024',
      href: null,
      sizeBytes,
      dateAdded: '2026-01-01T00:00:00Z',
      lastPlayedAt: '2026-06-01T00:00:00Z',
      recommended: true,
      reasons: [{ code: 'watched_movie_expired', evidence: { retentionDays: 30 } }],
    }],
    blocked: [],
    unresolved: [],
    warnings: ['Safe candidates cannot currently restore the configured free-space target.'],
  };
}

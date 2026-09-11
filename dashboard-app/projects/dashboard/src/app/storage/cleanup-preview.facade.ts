import { DestroyRef, Injectable, computed, inject, signal } from '@angular/core';

import { MEDIA_STACK_API } from '../media-stack/media-stack-api';
import {
  CLEANUP_PINS_STORAGE_KEY,
  CLEANUP_POLICY_STORAGE_KEY,
  CleanupPolicySettings,
  CleanupPreview,
  CleanupPreviewRequest,
  DEFAULT_CLEANUP_POLICY,
  GIB,
  cloneCleanupPolicy,
} from './cleanup.models';

export type CleanupPreviewPhase = 'idle' | 'loading' | 'ready' | 'stale' | 'error';

@Injectable()
export class CleanupPreviewFacade {
  private readonly api = inject(MEDIA_STACK_API);
  private readonly destroyRef = inject(DestroyRef);
  private readonly policyState = signal(loadPolicy());
  private readonly pinState = signal(loadPins());
  private readonly previewState = signal<CleanupPreview | null>(null);
  private readonly phaseState = signal<CleanupPreviewPhase>('idle');
  private readonly errorState = signal('');
  private readonly warningState = signal('');
  private requestSerial = 0;
  private controller: AbortController | null = null;
  private successfulFingerprint = '';

  readonly policy = this.policyState.asReadonly();
  readonly pinnedIds = this.pinState.asReadonly();
  readonly preview = this.previewState.asReadonly();
  readonly phase = this.phaseState.asReadonly();
  readonly error = this.errorState.asReadonly();
  readonly warning = this.warningState.asReadonly();
  readonly isLoading = computed(() => this.phaseState() === 'loading');
  readonly isStale = computed(() => this.phaseState() === 'stale');
  readonly hasPreview = computed(() => this.previewState() !== null);

  constructor() {
    this.destroyRef.onDestroy(() => {
      this.requestSerial += 1;
      this.controller?.abort();
    });
  }

  async runPreview(): Promise<void> {
    const method = this.api.previewStorageCleanup;
    if (!method) {
      this.failRequest(new Error('Cleanup preview is unavailable in this environment'));
      return;
    }
    this.controller?.abort();
    const controller = new AbortController();
    this.controller = controller;
    const serial = ++this.requestSerial;
    const request = this.currentRequest();
    const fingerprint = JSON.stringify(request);
    this.phaseState.set('loading');
    this.errorState.set('');
    this.warningState.set('');

    try {
      const preview = await method.call(this.api, request, controller.signal);
      if (controller.signal.aborted || serial !== this.requestSerial) return;
      this.previewState.set(preview);
      this.successfulFingerprint = fingerprint;
      this.phaseState.set('ready');
      this.errorState.set('');
      this.warningState.set(preview.warnings.join(' '));
    } catch (error: unknown) {
      if (controller.signal.aborted || isAbortError(error) || serial !== this.requestSerial) return;
      this.failRequest(error);
    } finally {
      if (serial === this.requestSerial) this.controller = null;
    }
  }

  setMoviesEnabled(enabled: boolean): void {
    this.updatePolicy((policy) => { policy.rules.watchedMovies.enabled = enabled; });
  }

  setEpisodesEnabled(enabled: boolean): void {
    this.updatePolicy((policy) => { policy.rules.watchedEpisodes.enabled = enabled; });
  }

  setLargeFilesEnabled(enabled: boolean): void {
    this.updatePolicy((policy) => { policy.rules.largeWatchedFiles.enabled = enabled; });
  }

  setMovieRetention(value: string): void {
    this.updateInteger(value, 0, 3650, (policy, parsed) => { policy.rules.watchedMovies.retentionDays = parsed; });
  }

  setEpisodeRetention(value: string): void {
    this.updateInteger(value, 0, 3650, (policy, parsed) => { policy.rules.watchedEpisodes.retentionDays = parsed; });
  }

  setKeepLatest(value: string): void {
    this.updateInteger(value, 0, 100, (policy, parsed) => { policy.rules.watchedEpisodes.keepLatestPerSeries = parsed; });
  }

  setTargetFreeGib(value: string): void {
    const gib = parseInteger(value, 0, 1_000_000);
    if (gib === null) return;
    this.updatePolicy((policy) => { policy.targetFreeBytes = gib * GIB; });
  }

  setLargeMinimumGib(value: string): void {
    const gib = parseInteger(value, 0, 1_000_000);
    if (gib === null) return;
    this.updatePolicy((policy) => { policy.rules.largeWatchedFiles.minimumBytes = gib * GIB; });
  }

  setLargeIdleDays(value: string): void {
    this.updateInteger(value, 0, 3650, (policy, parsed) => { policy.rules.largeWatchedFiles.idleDays = parsed; });
  }

  setRecentGraceDays(value: string): void {
    this.updateInteger(value, 0, 3650, (policy, parsed) => { policy.protections.recentAdditionGraceDays = parsed; });
  }

  keepCandidate(id: string): void {
    if (!/^sg_[0-9a-f]{24}$/.test(id) || this.pinState().includes(id)) return;
    const next = [...this.pinState(), id].slice(0, 5000);
    this.pinState.set(next);
    writeStorage(CLEANUP_PINS_STORAGE_KEY, { schemaVersion: 1, ids: next });
    this.invalidate();
  }

  unkeepCandidate(id: string): void {
    const next = this.pinState().filter((candidateId) => candidateId !== id);
    if (next.length === this.pinState().length) return;
    this.pinState.set(next);
    writeStorage(CLEANUP_PINS_STORAGE_KEY, { schemaVersion: 1, ids: next });
    this.invalidate();
  }

  isPinned(id: string): boolean {
    return this.pinState().includes(id);
  }

  private updateInteger(
    value: string,
    minimum: number,
    maximum: number,
    mutate: (policy: CleanupPolicySettings, parsed: number) => void,
  ): void {
    const parsed = parseInteger(value, minimum, maximum);
    if (parsed === null) return;
    this.updatePolicy((policy) => mutate(policy, parsed));
  }

  private updatePolicy(mutate: (policy: CleanupPolicySettings) => void): void {
    const next = cloneCleanupPolicy(this.policyState());
    mutate(next);
    this.policyState.set(next);
    writeStorage(CLEANUP_POLICY_STORAGE_KEY, next);
    this.invalidate();
  }

  private invalidate(): void {
    this.requestSerial += 1;
    this.controller?.abort();
    this.controller = null;
    this.errorState.set('');
    if (this.previewState()) {
      const stale = JSON.stringify(this.currentRequest()) !== this.successfulFingerprint;
      this.phaseState.set(stale ? 'stale' : 'ready');
      this.warningState.set(stale ? 'Settings changed. Run preview again to refresh the simulation.' : '');
    } else {
      this.phaseState.set('idle');
      this.warningState.set('');
    }
  }

  private currentRequest(): CleanupPreviewRequest {
    const policy = this.policyState();
    return {
      schemaVersion: 1,
      targetFreeBytes: policy.targetFreeBytes,
      rules: {
        watchedMovies: { ...policy.rules.watchedMovies },
        watchedEpisodes: { ...policy.rules.watchedEpisodes },
        largeWatchedFiles: { ...policy.rules.largeWatchedFiles },
      },
      protections: {
        recentAdditionGraceDays: policy.protections.recentAdditionGraceDays,
        pinnedCandidateIds: [...this.pinState()].sort(),
      },
    };
  }

  private failRequest(error: unknown): void {
    const message = error instanceof Error && error.message.trim()
      ? error.message.trim()
      : 'Cleanup preview failed. Try again.';
    if (this.previewState()) {
      this.phaseState.set(JSON.stringify(this.currentRequest()) === this.successfulFingerprint ? 'ready' : 'stale');
      this.warningState.set(`Could not refresh cleanup preview. Showing the last successful simulation. ${message}`);
      return;
    }
    this.phaseState.set('error');
    this.errorState.set(message);
  }
}

function parseInteger(value: string, minimum: number, maximum: number): number | null {
  const normalized = value.trim().replace(/\s*(days?|episodes?|gib|gb)$/i, '');
  if (!/^\d+$/.test(normalized)) return null;
  const parsed = Number(normalized);
  return Number.isSafeInteger(parsed) && parsed >= minimum && parsed <= maximum ? parsed : null;
}

function loadPolicy(): CleanupPolicySettings {
  const fallback = cloneCleanupPolicy(DEFAULT_CLEANUP_POLICY);
  const stored = readStorage(CLEANUP_POLICY_STORAGE_KEY);
  if (!stored) return fallback;
  try {
    const value = stored as Record<string, unknown>;
    if (value['schemaVersion'] !== 1 || !isRecord(value['rules']) || !isRecord(value['protections'])) throw new Error();
    const rules = value['rules'];
    const movies = rules['watchedMovies'];
    const episodes = rules['watchedEpisodes'];
    const large = rules['largeWatchedFiles'];
    if (!isRecord(movies) || !isRecord(episodes) || !isRecord(large)) throw new Error();
    const policy: CleanupPolicySettings = {
      schemaVersion: 1,
      targetFreeBytes: integer(value['targetFreeBytes'], 0, Number.MAX_SAFE_INTEGER),
      rules: {
        watchedMovies: {
          enabled: bool(movies['enabled']),
          retentionDays: integer(movies['retentionDays'], 0, 3650),
        },
        watchedEpisodes: {
          enabled: bool(episodes['enabled']),
          retentionDays: integer(episodes['retentionDays'], 0, 3650),
          keepLatestPerSeries: integer(episodes['keepLatestPerSeries'], 0, 100),
        },
        largeWatchedFiles: {
          enabled: bool(large['enabled']),
          minimumBytes: integer(large['minimumBytes'], 0, Number.MAX_SAFE_INTEGER),
          idleDays: integer(large['idleDays'], 0, 3650),
        },
      },
      protections: { recentAdditionGraceDays: integer(value['protections'] && (value['protections'] as Record<string, unknown>)['recentAdditionGraceDays'], 0, 3650) },
    };
    return policy;
  } catch {
    removeStorage(CLEANUP_POLICY_STORAGE_KEY);
    return fallback;
  }
}

function loadPins(): string[] {
  const stored = readStorage(CLEANUP_PINS_STORAGE_KEY);
  if (!stored) return [];
  try {
    const value = stored as Record<string, unknown>;
    const ids = value['ids'];
    if (value['schemaVersion'] !== 1 || !Array.isArray(ids) || ids.length > 5000) throw new Error();
    const normalized = ids.filter((id): id is string => typeof id === 'string' && /^sg_[0-9a-f]{24}$/.test(id));
    if (normalized.length !== ids.length) throw new Error();
    return [...new Set(normalized)].sort();
  } catch {
    removeStorage(CLEANUP_PINS_STORAGE_KEY);
    return [];
  }
}

function readStorage(key: string): unknown | null {
  try {
    const raw = globalThis.localStorage?.getItem(key);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function writeStorage(key: string, value: unknown): void {
  try { globalThis.localStorage?.setItem(key, JSON.stringify(value)); } catch { /* Browser storage is best-effort. */ }
}

function removeStorage(key: string): void {
  try { globalThis.localStorage?.removeItem(key); } catch { /* Browser storage is best-effort. */ }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function integer(value: unknown, minimum: number, maximum: number): number {
  if (typeof value !== 'number' || !Number.isSafeInteger(value) || value < minimum || value > maximum) throw new Error();
  return value;
}

function bool(value: unknown): boolean {
  if (typeof value !== 'boolean') throw new Error();
  return value;
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}

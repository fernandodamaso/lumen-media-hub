import { WritableSignal } from '@angular/core';
import { ScheduledPollController } from './scheduled-poll';

/** Shared load lifecycle status used by polled facades. */
export type PolledFacadeStatus = 'loading' | 'ready' | 'empty' | 'error';

/** True for first paint / recovery refreshes that may clear prior payload. */
export function isInitialRefresh(status: PolledFacadeStatus, optionsInitial?: boolean): boolean {
  return optionsInitial === true || status === 'loading' || status === 'error';
}

/**
 * Soft-fail when a background refresh fails after ready/empty data exists;
 * otherwise hard-fail to error and optionally clear payload on initial load.
 */
export function applyPolledRefreshFailure(args: {
  initial: boolean;
  status: WritableSignal<PolledFacadeStatus>;
  error: WritableSignal<string>;
  refreshError: string;
  loadError: string;
  clearPayload?: () => void;
  backendMessage?: string;
}): void {
  const hasPrior = args.status() === 'ready' || args.status() === 'empty';
  if (!args.initial && hasPrior) {
    args.error.set(args.refreshError);
    return;
  }
  args.status.set('error');
  args.error.set(args.backendMessage || args.loadError);
  if (args.initial) {
    args.clearPayload?.();
  }
}

/**
 * Run one poll-generation refresh with abort-safe catch/finally bookkeeping.
 * Domain success commits stay in the facade `load` callback.
 */
export async function runPolledRefresh(args: {
  poll: ScheduledPollController;
  refreshing: WritableSignal<boolean>;
  signal?: AbortSignal;
  load: (requestId: number) => Promise<void>;
  onFailure: () => void;
}): Promise<void> {
  args.refreshing.set(true);
  const requestId = args.poll.beginRequest();
  try {
    await args.load(requestId);
  } catch {
    if (!args.poll.isCurrent(requestId)) return;
    // Cancelled refreshes must not mutate facade state; callers apply timeout/teardown policy.
    if (args.signal?.aborted) return;
    args.onFailure();
  } finally {
    if (args.poll.isCurrent(requestId)) args.refreshing.set(false);
  }
}

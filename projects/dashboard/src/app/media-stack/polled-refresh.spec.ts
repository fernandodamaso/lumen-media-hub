import { signal } from '@angular/core';
import {
  applyPolledRefreshFailure,
  isInitialRefresh,
  runPolledRefresh,
} from './polled-refresh';
import { ScheduledPollController } from './scheduled-poll';

describe('polled-refresh helpers', () => {
  it('isInitialRefresh treats loading/error and explicit initial as initial', () => {
    expect(isInitialRefresh('loading')).toBe(true);
    expect(isInitialRefresh('error')).toBe(true);
    expect(isInitialRefresh('ready', true)).toBe(true);
    expect(isInitialRefresh('ready')).toBe(false);
    expect(isInitialRefresh('empty')).toBe(false);
  });

  it('applyPolledRefreshFailure soft-fails when prior data exists', () => {
    const status = signal<'loading' | 'ready' | 'empty' | 'error'>('ready');
    const error = signal('');
    let cleared = false;
    applyPolledRefreshFailure({
      initial: false,
      status,
      error,
      refreshError: 'soft',
      loadError: 'hard',
      clearPayload: () => {
        cleared = true;
      },
    });
    expect(status()).toBe('ready');
    expect(error()).toBe('soft');
    expect(cleared).toBe(false);
  });

  it('applyPolledRefreshFailure hard-fails and clears on initial', () => {
    const status = signal<'loading' | 'ready' | 'empty' | 'error'>('loading');
    const error = signal('');
    let cleared = false;
    applyPolledRefreshFailure({
      initial: true,
      status,
      error,
      refreshError: 'soft',
      loadError: 'hard',
      backendMessage: 'backend',
      clearPayload: () => {
        cleared = true;
      },
    });
    expect(status()).toBe('error');
    expect(error()).toBe('backend');
    expect(cleared).toBe(true);
  });

  it('runPolledRefresh ignores aborted failures and clears refreshing', async () => {
    const poll = new ScheduledPollController();
    const refreshing = signal(false);
    const abort = new AbortController();
    abort.abort();
    let failed = false;
    await runPolledRefresh({
      poll,
      refreshing,
      signal: abort.signal,
      load: () => Promise.reject(new Error('aborted')),
      onFailure: () => {
        failed = true;
      },
    });
    expect(failed).toBe(false);
    expect(refreshing()).toBe(false);
  });

  it('runPolledRefresh reports non-abort failures', async () => {
    const poll = new ScheduledPollController();
    const refreshing = signal(false);
    let failed = false;
    await runPolledRefresh({
      poll,
      refreshing,
      load: () => Promise.reject(new Error('network')),
      onFailure: () => {
        failed = true;
      },
    });
    expect(failed).toBe(true);
    expect(refreshing()).toBe(false);
  });
});

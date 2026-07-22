import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  SCHEDULED_REFRESH_TIMEOUT_MS,
  ScheduledPollController,
} from './scheduled-poll';

describe('ScheduledPollController', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('startRefreshing wires interval ticks through abortable run', async () => {
    const poll = new ScheduledPollController();
    const onTimeout = vi.fn();
    let seenSignal: AbortSignal | undefined;

    poll.startRefreshing(
      60_000,
      async ({ signal }) => {
        seenSignal = signal;
        poll.beginRequest();
        await new Promise<void>((_, reject) => {
          signal.addEventListener(
            'abort',
            () => { reject(new DOMException('The operation was aborted.', 'AbortError')); },
            { once: true },
          );
        }).catch(() => undefined);
      },
      () => {
        onTimeout();
      },
    );

    expect(seenSignal?.aborted).toBe(false);
    await vi.advanceTimersByTimeAsync(SCHEDULED_REFRESH_TIMEOUT_MS);
    expect(seenSignal?.aborted).toBe(true);
    expect(onTimeout).toHaveBeenCalledTimes(1);
  });

  it('starts once, ticks immediately, then on the interval', async () => {
    const poll = new ScheduledPollController();
    const tick = vi.fn(() => Promise.resolve(undefined));

    expect(poll.start(1_000, tick)).toBe(true);
    expect(poll.start(1_000, tick)).toBe(false);
    expect(tick).toHaveBeenCalledTimes(1);
    expect(tick).toHaveBeenLastCalledWith(true);

    await vi.advanceTimersByTimeAsync(1_000);
    expect(tick).toHaveBeenCalledTimes(2);
    expect(tick).toHaveBeenLastCalledWith(false);

    poll.stop();
    await vi.advanceTimersByTimeAsync(5_000);
    expect(tick).toHaveBeenCalledTimes(2);
  });

  it('aborts hung scheduled work and invokes onTimeout when still owning', async () => {
    const poll = new ScheduledPollController();
    const onTimeout = vi.fn();
    let seenSignal: AbortSignal | undefined;

    // Arm polling first so timeout failure is eligible (requires pollHandle).
    poll.start(60_000, () => undefined);

    const running = poll.run(async (signal) => {
      seenSignal = signal;
      poll.beginRequest();
      await new Promise<void>((_, reject) => {
        signal.addEventListener(
          'abort',
          () => { reject(new DOMException('The operation was aborted.', 'AbortError')); },
          { once: true },
        );
      }).catch(() => undefined);
    }, onTimeout);

    expect(seenSignal?.aborted).toBe(false);
    await vi.advanceTimersByTimeAsync(SCHEDULED_REFRESH_TIMEOUT_MS);
    await running;
    expect(seenSignal?.aborted).toBe(true);
    expect(onTimeout).toHaveBeenCalledTimes(1);
  });

  it('skips overlapping scheduled runs while one is in flight', async () => {
    const poll = new ScheduledPollController();
    let release!: () => void;
    const hung = new Promise<void>((resolve) => {
      release = resolve;
    });
    const refresh = vi.fn(async (signal: AbortSignal) => {
      poll.beginRequest();
      await Promise.race([
        hung,
        new Promise<void>((_, reject) => {
          signal.addEventListener('abort', () => { reject(new DOMException('aborted', 'AbortError')); }, {
            once: true,
          });
        }),
      ]).catch(() => undefined);
    });

    const first = poll.run(refresh, () => undefined);
    const second = poll.run(refresh, () => undefined);
    await Promise.resolve();
    expect(refresh).toHaveBeenCalledTimes(1);

    release();
    await first;
    await second;
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it('does not invoke onTimeout after stop invalidates ownership', async () => {
    const poll = new ScheduledPollController();
    const onTimeout = vi.fn();
    let release!: () => void;
    const hung = new Promise<void>((resolve) => {
      release = resolve;
    });

    poll.start(60_000, () => undefined);
    const running = poll.run(async (signal) => {
      poll.beginRequest();
      await Promise.race([
        hung,
        new Promise<void>((_, reject) => {
          signal.addEventListener('abort', () => { reject(new DOMException('aborted', 'AbortError')); }, {
            once: true,
          });
        }),
      ]).catch(() => undefined);
    }, onTimeout);

    poll.stop();
    await vi.advanceTimersByTimeAsync(SCHEDULED_REFRESH_TIMEOUT_MS);
    release();
    await running;
    expect(onTimeout).not.toHaveBeenCalled();
  });
});

/** Bound scheduled polls so a hung request cannot lock out later ticks. */
export const SCHEDULED_REFRESH_TIMEOUT_MS = 15_000;

/**
 * Shared interval + abort-timeout controller for facade polling.
 * Owns request generations so overlapping refreshes and teardown stay race-safe.
 */
export class ScheduledPollController {
  private requestId = 0;
  private scheduledInFlight = false;
  private pollHandle?: ReturnType<typeof setInterval>;
  private refreshAbort?: AbortController;
  private refreshTimeoutId?: ReturnType<typeof setTimeout>;

  /** True while the interval is armed (not stopped / destroyed). */
  get armed(): boolean {
    return this.pollHandle !== undefined;
  }

  /** Bump generation for a new refresh attempt; use with {@link isCurrent}. */
  beginRequest(): number {
    return ++this.requestId;
  }

  isCurrent(requestId: number): boolean {
    return requestId === this.requestId;
  }

  /**
   * Arm polling: fire one immediate tick, then repeat on `intervalMs`.
   * No-ops when already armed. Returns whether polling was started.
   */
  start(intervalMs: number, tick: (initial: boolean) => void | Promise<void>): boolean {
    if (this.pollHandle) return false;
    void tick(true);
    this.pollHandle = setInterval(() => void tick(false), intervalMs);
    return true;
  }

  /**
   * Arm interval polling that runs `refresh` with an abort timeout each tick.
   * `onTimeout` runs only when the timed-out attempt still owns the generation
   * and polling has not been stopped.
   */
  startRefreshing(
    intervalMs: number,
    refresh: (options: { initial: boolean; signal: AbortSignal }) => Promise<void>,
    onTimeout: (initial: boolean) => void,
  ): boolean {
    return this.start(intervalMs, (initial) =>
      this.run((signal) => refresh({ initial, signal }), () => {
        onTimeout(initial);
      }),
    );
  }

  /**
   * Run one scheduled refresh with overlap guard + abort timeout.
   * On timeout, `onTimeout` runs only when this attempt still owns the generation
   * and polling has not been stopped.
   */
  async run(
    refresh: (signal: AbortSignal) => Promise<void>,
    onTimeout: () => void,
  ): Promise<void> {
    if (this.scheduledInFlight) return;
    this.scheduledInFlight = true;
    const abort = new AbortController();
    this.refreshAbort = abort;
    this.refreshTimeoutId = setTimeout(() => {
      abort.abort();
    }, SCHEDULED_REFRESH_TIMEOUT_MS);
    const priorRequestId = this.requestId;
    try {
      await refresh(abort.signal);
      // Only the owning attempt may surface timeout failure after a superseded newer refresh.
      const ownedRequestId = priorRequestId + 1;
      if (abort.signal.aborted && this.pollHandle !== undefined && this.requestId === ownedRequestId) {
        onTimeout();
      }
    } finally {
      clearTimeout(this.refreshTimeoutId);
      this.refreshTimeoutId = undefined;
      if (this.refreshAbort === abort) {
        this.refreshAbort = undefined;
      }
      this.scheduledInFlight = false;
    }
  }

  /** Clear interval/timeout, invalidate generation, and abort any in-flight refresh. */
  stop(): void {
    if (this.pollHandle) clearInterval(this.pollHandle);
    this.pollHandle = undefined;
    clearTimeout(this.refreshTimeoutId);
    this.refreshTimeoutId = undefined;
    // Invalidate before abort so a racing settle cannot write after teardown.
    this.requestId += 1;
    this.refreshAbort?.abort();
    this.refreshAbort = undefined;
    this.scheduledInFlight = false;
  }
}

/** Shared runtime shape checks for HTTP adapter payloads. */

export interface OkEnvelope {
  ok: boolean;
  error?: string;
}

/** Ok envelope plus open string index — preserves extra wire fields after `ok` is checked. */
export type OkEnvelopeRecord = OkEnvelope & Record<string, unknown>;

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isOkEnvelopeRecord(data: Record<string, unknown>): data is OkEnvelopeRecord {
  return typeof data['ok'] === 'boolean';
}

/** Reject null, primitives, arrays, and objects that lack a boolean `ok`. */
export function requireOkEnvelope(data: unknown, fallback: string): OkEnvelopeRecord {
  if (!isRecord(data) || !isOkEnvelopeRecord(data)) {
    throw new Error(fallback);
  }
  return data;
}

/** Soft envelopes keep `{ ok: false }` for facade handling but reject malformed shapes.
 * Payload validators run only on successful envelopes. */
export function requireSoftEnvelope<T extends OkEnvelope>(
  data: unknown,
  fallback: string,
  validate?: (envelope: T) => void,
): T {
  const envelope = requireOkEnvelope(data, fallback);
  // Caller supplies T via validate / generic — wire extras remain on the same object.
  const typed = envelope as T;
  if (typed.ok) {
    validate?.(typed);
  }
  return typed;
}

/** Hard envelopes throw when `ok === false`. */
export function requireHardEnvelope(data: unknown, fallback: string): OkEnvelopeRecord {
  const envelope = requireOkEnvelope(data, fallback);
  if (!envelope.ok) {
    throw new Error(envelope.error || fallback);
  }
  return envelope;
}

export function requireArrayField(
  data: Record<string, unknown>,
  field: string,
  fallback: string,
): unknown[] {
  const value = data[field];
  if (!Array.isArray(value)) {
    throw new Error(fallback);
  }
  return value;
}

/** True for DOMException/Error AbortError — used so cancellation is not mistaken for soft failure. */
export function isAbortError(error: unknown): boolean {
  return (
    (typeof DOMException !== 'undefined' &&
      error instanceof DOMException &&
      error.name === 'AbortError') ||
    (error instanceof Error && error.name === 'AbortError')
  );
}

/** Require a non-empty trimmed string; never invent an identity or label. */
export function requireNonEmptyString(
  value: unknown,
  context: string,
): string {
  if (typeof value !== 'string' || !value.trim()) {
    throw new Error(context);
  }
  return value.trim();
}

/** Require a parseable ISO / Date-parseable timestamp string from the backend. */
export function requireIsoTimestamp(value: unknown, context: string): string {
  const text = requireNonEmptyString(value, context);
  if (Number.isNaN(Date.parse(text))) {
    throw new Error(context);
  }
  return text;
}

/**
 * Validate GET /cron/logs success payloads before domain mapping.
 * Soft `{ ok: false }` envelopes skip this (handled by requireSoftEnvelope).
 */
export function requireCronLogsPayload(data: Record<string, unknown>): void {
  requireIsoTimestamp(
    data['generatedAt'],
    'Malformed cron logs response: missing generatedAt',
  );
  const logs = requireArrayField(data, 'logs', 'Malformed cron logs response');
  logs.forEach((entry, index) => {
    if (!isRecord(entry)) {
      throw new Error(`Malformed cron logs response: member ${index} is not an object`);
    }
    requireNonEmptyString(
      entry['id'],
      `Malformed cron logs response: member ${index} is missing id`,
    );
    requireNonEmptyString(
      entry['title'],
      `Malformed cron logs response: member ${index} is missing title`,
    );
    const runs = entry['runs'];
    if (runs === undefined || runs === null) return;
    if (!Array.isArray(runs)) {
      throw new Error(`Malformed cron logs response: member ${index} has invalid runs`);
    }
    runs.forEach((run, runIndex) => {
      if (!isRecord(run)) {
        throw new Error(
          `Malformed cron logs response: member ${index} run ${runIndex} is not an object`,
        );
      }
      requireIsoTimestamp(
        run['timestamp'],
        `Malformed cron logs response: member ${index} run ${runIndex} is missing timestamp`,
      );
    });
  });
}

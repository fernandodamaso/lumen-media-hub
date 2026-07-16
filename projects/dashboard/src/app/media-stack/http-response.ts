/** Shared runtime shape checks for HTTP adapter payloads. */

export interface OkEnvelope {
  ok: boolean;
  error?: string;
}

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** Reject null, primitives, arrays, and objects that lack a boolean `ok`. */
export function requireOkEnvelope(data: unknown, fallback: string): OkEnvelope {
  if (!isRecord(data) || typeof data['ok'] !== 'boolean') {
    throw new Error(fallback);
  }
  return data as unknown as OkEnvelope;
}

/** Soft envelopes keep `{ ok: false }` for facade handling but reject malformed shapes.
 * Payload validators run only on successful envelopes. */
export function requireSoftEnvelope<T extends OkEnvelope>(
  data: unknown,
  fallback: string,
  validate?: (envelope: T) => void,
): T {
  const envelope = requireOkEnvelope(data, fallback) as T;
  if (envelope.ok === true) {
    validate?.(envelope);
  }
  return envelope;
}

/** Hard envelopes throw when `ok === false`. */
export function requireHardEnvelope<T extends OkEnvelope>(data: unknown, fallback: string): T {
  const envelope = requireOkEnvelope(data, fallback) as T;
  if (envelope.ok === false) {
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

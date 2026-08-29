import { claimedJobSchema, type ClaimedJob, type Pick } from './contracts.js';

const allowedCodes = new Set(['invalid_output', 'model_timeout', 'provider_failure']);

export interface WorkerDependencies {
  baseUrl: string;
  token: string;
  fetcher?: typeof fetch;
  recommend: (job: ClaimedJob) => Promise<Pick[]>;
}

function headers(token: string, lease?: string): HeadersInit {
  return {
    'Content-Type': 'application/json',
    'X-Actions-Token': token,
    ...(lease ? { 'X-AI-Lease-Token': lease } : {}),
  };
}

export async function processOnce(deps: WorkerDependencies): Promise<boolean> {
  const fetcher = deps.fetcher ?? fetch;
  const claimed = await fetcher(`${deps.baseUrl}/internal/ai-picks/jobs/claim`, {
    method: 'POST', headers: headers(deps.token), body: '{}',
  });
  if (!claimed.ok) throw new Error(`claim failed: ${claimed.status}`);
  const envelope = await claimed.json() as { job?: unknown };
  if (envelope.job == null) return false;
  const job = claimedJobSchema.parse(envelope.job);
  try {
    const picks = await deps.recommend(job);
    const completed = await fetcher(`${deps.baseUrl}/internal/ai-picks/jobs/${encodeURIComponent(job.id)}/complete`, {
      method: 'POST', headers: headers(deps.token, job.lease_token), body: JSON.stringify({ picks }),
    });
    if (!completed.ok && completed.status !== 409) throw new Error(`complete failed: ${completed.status}`);
  } catch (error) {
    const possible = error && typeof error === 'object' && 'code' in error ? String(error.code) : '';
    const code = allowedCodes.has(possible) ? possible : 'provider_failure';
    const failed = await fetcher(`${deps.baseUrl}/internal/ai-picks/jobs/${encodeURIComponent(job.id)}/fail`, {
      method: 'POST', headers: headers(deps.token, job.lease_token), body: JSON.stringify({ code }),
    });
    if (!failed.ok && failed.status !== 409) throw new Error(`fail failed: ${failed.status}`);
  }
  return true;
}

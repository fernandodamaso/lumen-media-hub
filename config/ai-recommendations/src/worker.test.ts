import { describe, expect, it, vi } from 'vitest';
import { processOnce } from './worker.js';

const job = {
  id: 'job-1', lease_token: 'lease', desired_count: 1,
  candidates: [{ identity: 'movie:42', type: 'movie' as const, tmdb_id: 42, title: 'Fixture' }],
  taste: {},
};

describe('processOnce', () => {
  it('claims and completes using the private lease header', async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    const fetcher = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      calls.push({ url: String(url), init });
      if (String(url).endsWith('/claim')) return new Response(JSON.stringify({ ok: true, job }));
      return new Response(JSON.stringify({ ok: true }));
    });

    const worked = await processOnce({
      baseUrl: 'http://backend:8085', token: 'actions', fetcher,
      recommend: async () => [{ identity: 'movie:42', reason: 'Fit.' }],
    });

    expect(worked).toBe(true);
    expect(calls[1]?.url).toContain('/job-1/complete');
    expect(new Headers(calls[1]?.init?.headers).get('X-AI-Lease-Token')).toBe('lease');
    expect(JSON.stringify(calls)).not.toContain('private-api-key');
  });

  it('reports only an allowlisted code when generation fails', async () => {
    const bodies: string[] = [];
    const fetcher = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      if (String(url).endsWith('/claim')) return new Response(JSON.stringify({ ok: true, job }));
      bodies.push(String(init?.body));
      return new Response(JSON.stringify({ ok: true }));
    });

    await processOnce({
      baseUrl: 'http://backend:8085', token: 'actions', fetcher,
      recommend: async () => { throw Object.assign(new Error('secret-value'), { code: 'provider_failure' }); },
    });

    expect(bodies[0]).toBe(JSON.stringify({ code: 'provider_failure' }));
  });

  it('recovers on the next poll after a transient claim failure', async () => {
    let claims = 0;
    const fetcher = vi.fn(async (url: string | URL | Request) => {
      if (String(url).endsWith('/claim')) {
        claims += 1;
        if (claims === 1) throw new Error('temporary backend failure');
        return new Response(JSON.stringify({ ok: true, job }));
      }
      return new Response(JSON.stringify({ ok: true }));
    });
    const options = {
      baseUrl: 'http://backend:8085', token: 'actions', fetcher,
      recommend: async () => [{ identity: 'movie:42', reason: 'Fit.' }],
    };

    await expect(processOnce(options)).rejects.toThrow('temporary backend failure');
    await expect(processOnce(options)).resolves.toBe(true);
  });
});

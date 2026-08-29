import { describe, expect, it } from 'vitest';
import { buildPrompt } from './prompt.js';
import type { ClaimedJob } from './contracts.js';

describe('buildPrompt', () => {
  it('requires the exact structured-output envelope without markdown', () => {
    const job: ClaimedJob = {
      id: 'job-1',
      lease_token: 'private',
      desired_count: 1,
      candidates: [{ identity: 'movie:42', type: 'movie', tmdb_id: 42, title: 'Fixture' }],
      taste: {},
    };

    const prompt = buildPrompt(job);
    expect(prompt).toContain('{"picks":[{"identity":"movie:42","reason":"Specific reason"}]}');
    expect(prompt).toContain('Do not return a bare array');
    expect(prompt).toContain('Do not use Markdown or code fences');
  });
});

import { describe, expect, it } from 'vitest';
import { MockLanguageModelV3 } from 'ai/test';
import { generatePicks } from './recommend.js';
import type { ClaimedJob } from './contracts.js';

const job: ClaimedJob = {
  id: 'job-1',
  lease_token: 'private-lease',
  desired_count: 1,
  candidates: [
    { identity: 'movie:42', type: 'movie', tmdb_id: 42, title: 'Fixture', year: 2024, overview: 'Story' },
  ],
  taste: { liked: [], disliked: [], watched: [], skipped: [] },
};

const usage = {
  inputTokens: { total: 1, noCache: 1, cacheRead: undefined, cacheWrite: undefined },
  outputTokens: { total: 1, text: 1, reasoning: undefined },
};

describe('generatePicks', () => {
  it('uses AI SDK structured output with a deterministic MockLanguageModelV3', async () => {
    const model = new MockLanguageModelV3({
      doGenerate: {
        content: [{ type: 'text', text: JSON.stringify({ picks: [{ identity: 'movie:42', reason: 'A fit.' }] }) }],
        finishReason: { unified: 'stop', raw: undefined }, usage, warnings: [],
      },
    });

    await expect(generatePicks(job, model, 1_000)).resolves.toEqual([
      { identity: 'movie:42', reason: 'A fit.' },
    ]);
    expect(model.doGenerateCalls[0]?.responseFormat?.type).toBe('json');
  });

  it('rejects unknown and duplicate identities after schema parsing', async () => {
    const unknown = new MockLanguageModelV3({
      doGenerate: {
        content: [{ type: 'text', text: JSON.stringify({ picks: [{ identity: 'movie:99', reason: 'No.' }] }) }],
        finishReason: { unified: 'stop', raw: undefined }, usage, warnings: [],
      },
    });
    await expect(generatePicks(job, unknown, 1_000)).rejects.toMatchObject({ code: 'invalid_output' });

    const duplicate = new MockLanguageModelV3({
      doGenerate: {
        content: [{ type: 'text', text: JSON.stringify({ picks: [
          { identity: 'movie:42', reason: 'One.' }, { identity: 'movie:42', reason: 'Two.' },
        ] }) }],
        finishReason: { unified: 'stop', raw: undefined }, usage, warnings: [],
      },
    });
    await expect(generatePicks(job, duplicate, 1_000)).rejects.toMatchObject({ code: 'invalid_output' });
  });

  it('rejects empty structured output', async () => {
    const model = new MockLanguageModelV3({
      doGenerate: {
        content: [{ type: 'text', text: JSON.stringify({ picks: [] }) }],
        finishReason: { unified: 'stop', raw: undefined }, usage, warnings: [],
      },
    });

    await expect(generatePicks(job, model, 1_000)).rejects.toMatchObject({ code: 'invalid_output' });
  });

  it('aborts a slow model with a sanitized timeout code', async () => {
    const model = new MockLanguageModelV3({
      doGenerate: async ({ abortSignal }) => new Promise((_, reject) => {
        abortSignal?.addEventListener('abort', () => reject(new Error('provider secret')), { once: true });
      }),
    });

    await expect(generatePicks(job, model, 5)).rejects.toMatchObject({ code: 'model_timeout' });
  });
});

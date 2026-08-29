import { describe, expect, it } from 'vitest';
import { createModel } from './providers.js';

describe('createModel', () => {
  it.each([
    ['openai', { AI_PROVIDER: 'openai', AI_MODEL: 'configured-model', OPENAI_API_KEY: 'secret' }],
    ['anthropic', { AI_PROVIDER: 'anthropic', AI_MODEL: 'configured-model', ANTHROPIC_API_KEY: 'secret' }],
    ['google', { AI_PROVIDER: 'google', AI_MODEL: 'configured-model', GOOGLE_GENERATIVE_AI_API_KEY: 'secret' }],
    ['openai-compatible', {
      AI_PROVIDER: 'openai-compatible', AI_MODEL: 'configured-model',
      AI_COMPATIBLE_BASE_URL: 'https://example.invalid/v1', AI_COMPATIBLE_API_KEY: 'secret',
      AI_COMPATIBLE_SUPPORTS_STRUCTURED_OUTPUTS: 'true',
    }],
  ])('creates the %s provider from configuration', (provider, env) => {
    const model = createModel(env);
    expect((model as { modelId: string }).modelId).toBe('configured-model');
    expect((model as { provider: string }).provider).toContain(provider === 'openai-compatible' ? 'compatible' : provider);
  });

  it('fails closed when provider, model, or native credential is missing', () => {
    expect(() => createModel({})).toThrow(/AI_PROVIDER/);
    expect(() => createModel({ AI_PROVIDER: 'openai' })).toThrow(/AI_MODEL/);
    expect(() => createModel({ AI_PROVIDER: 'openai', AI_MODEL: 'configured-model' })).toThrow(/OPENAI_API_KEY/);
  });

  it('forces non-streaming responses for compatible generate calls', () => {
    const model = createModel({
      AI_PROVIDER: 'openai-compatible',
      AI_MODEL: 'configured-model',
      AI_COMPATIBLE_BASE_URL: 'https://example.invalid/v1',
      AI_COMPATIBLE_API_KEY: 'secret',
    }) as unknown as {
      config: { transformRequestBody: (body: Record<string, unknown>) => Record<string, unknown> };
    };

    expect(model.config.transformRequestBody({ model: 'configured-model' }).stream).toBe(false);
    expect(model.config.transformRequestBody({ model: 'configured-model', stream: true }).stream).toBe(true);
  });
});

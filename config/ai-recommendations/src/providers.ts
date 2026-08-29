import type { LanguageModel } from 'ai';
import { createOpenAI } from '@ai-sdk/openai';
import { createAnthropic } from '@ai-sdk/anthropic';
import { createGoogle } from '@ai-sdk/google';
import { createOpenAICompatible } from '@ai-sdk/openai-compatible';

type Environment = Record<string, string | undefined>;

function required(env: Environment, name: string): string {
  const value = env[name]?.trim();
  if (!value) throw new Error(`${name} is required`);
  return value;
}

function enabled(value: string | undefined): boolean {
  return ['1', 'true', 'yes', 'on'].includes(value?.trim().toLowerCase() ?? '');
}

export function createModel(env: Environment = process.env): LanguageModel {
  const provider = required(env, 'AI_PROVIDER');
  const modelId = required(env, 'AI_MODEL');
  switch (provider) {
    case 'openai':
      return createOpenAI({ apiKey: required(env, 'OPENAI_API_KEY') })(modelId);
    case 'anthropic':
      return createAnthropic({ apiKey: required(env, 'ANTHROPIC_API_KEY') })(modelId);
    case 'google':
      return createGoogle({ apiKey: required(env, 'GOOGLE_GENERATIVE_AI_API_KEY') })(modelId);
    case 'openai-compatible':
      return createOpenAICompatible({
        name: 'openai-compatible',
        baseURL: required(env, 'AI_COMPATIBLE_BASE_URL'),
        apiKey: required(env, 'AI_COMPATIBLE_API_KEY'),
        supportsStructuredOutputs: enabled(env.AI_COMPATIBLE_SUPPORTS_STRUCTURED_OUTPUTS),
        transformRequestBody: body => ({ ...body, stream: body.stream ?? false }),
      })(modelId);
    default:
      throw new Error('AI_PROVIDER must be openai, anthropic, google, or openai-compatible');
  }
}

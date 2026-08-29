import {
  generateText,
  NoObjectGeneratedError,
  NoOutputGeneratedError,
  Output,
  type LanguageModel,
} from 'ai';
import { picksOutputSchema, type ClaimedJob, type Pick } from './contracts.js';
import { buildPrompt } from './prompt.js';

export class RecommendationFailure extends Error {
  constructor(public readonly code: 'invalid_output' | 'model_timeout' | 'provider_failure') {
    super(code);
  }
}

export async function generatePicks(
  job: ClaimedJob,
  model: LanguageModel,
  timeoutMs: number,
): Promise<Pick[]> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const result = await generateText({
      model,
      output: Output.object({ schema: picksOutputSchema }),
      prompt: buildPrompt(job),
      abortSignal: controller.signal,
    });
    const allPicks = result.output.picks;
    const allowed = new Set(job.candidates.map(candidate => candidate.identity));
    const seen = new Set<string>();
    for (const pick of allPicks) {
      if (!allowed.has(pick.identity) || seen.has(pick.identity)) {
        throw new RecommendationFailure('invalid_output');
      }
      seen.add(pick.identity);
    }
    if (allPicks.length === 0) throw new RecommendationFailure('invalid_output');
    return allPicks.slice(0, job.desired_count);
  } catch (error) {
    if (error instanceof RecommendationFailure) throw error;
    if (controller.signal.aborted) throw new RecommendationFailure('model_timeout');
    if (
      NoObjectGeneratedError.isInstance(error)
      || NoOutputGeneratedError.isInstance(error)
    ) {
      throw new RecommendationFailure('invalid_output');
    }
    throw new RecommendationFailure('provider_failure');
  } finally {
    clearTimeout(timer);
  }
}

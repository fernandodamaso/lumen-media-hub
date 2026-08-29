import type { ClaimedJob } from './contracts.js';

export function buildPrompt(job: ClaimedJob): string {
  return [
    'Choose personalized media picks only from the supplied eligible candidates.',
    `Return at most ${job.desired_count} picks. Every reason must be specific, concise, and at most 240 characters.`,
    'Do not invent identities or metadata. Return only identity and reason.',
    'Return exactly one JSON object shaped like {"picks":[{"identity":"movie:42","reason":"Specific reason"}]}. Do not return a bare array. Do not use Markdown or code fences.',
    JSON.stringify({ candidates: job.candidates, taste: job.taste }),
  ].join('\n\n');
}

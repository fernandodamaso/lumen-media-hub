import { z } from 'zod';

export const candidateSchema = z.object({
  identity: z.string().regex(/^(movie|tv):[1-9][0-9]*$/),
  type: z.enum(['movie', 'tv']),
  tmdb_id: z.number().int().positive(),
  title: z.string().min(1),
  year: z.number().int().nullable().optional(),
  overview: z.string().optional(),
  rating: z.number().nullable().optional(),
  signals: z.array(z.string()).optional(),
}).passthrough();

export const claimedJobSchema = z.object({
  id: z.string().min(1),
  lease_token: z.string().min(1),
  desired_count: z.number().int().positive().max(100),
  candidates: z.array(candidateSchema).min(1).max(100),
  taste: z.record(z.string(), z.unknown()),
});

export const picksOutputSchema = z.object({
  picks: z.array(z.object({
    identity: z.string().regex(/^(movie|tv):[1-9][0-9]*$/),
    reason: z.string().trim().min(1).max(240),
  })).min(1).max(100),
});

export type ClaimedJob = z.infer<typeof claimedJobSchema>;
export type Pick = z.infer<typeof picksOutputSchema>['picks'][number];

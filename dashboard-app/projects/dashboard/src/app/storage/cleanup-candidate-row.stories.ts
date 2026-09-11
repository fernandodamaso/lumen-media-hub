import type { Meta, StoryObj } from '@storybook/angular';

import { CleanupCandidateRow } from './cleanup-candidate-row';
import { CleanupCandidate, GIB } from './cleanup.models';

const candidate: CleanupCandidate = {
  id: 'sg_111111111111111111111111',
  mediaKind: 'movie',
  title: 'Dune: Part Two',
  subtitle: 'Movie · 2024',
  href: 'http://127.0.0.1:8096/web/index.html#!/details?id=demo-1',
  sizeBytes: Math.round(31.2 * GIB),
  dateAdded: '2026-02-10T12:00:00Z',
  lastPlayedAt: '2026-05-14T12:00:00Z',
  recommended: true,
  reasons: [
    { code: 'watched_movie_expired', evidence: { retentionDays: 30 } },
    { code: 'large_watched_file_stale', evidence: { minimumBytes: 20 * GIB, idleDays: 90 } },
  ],
};

const meta: Meta<CleanupCandidateRow> = {
  title: 'Features/Storage/Cleanup Candidate Row',
  component: CleanupCandidateRow,
  tags: ['autodocs'],
  parameters: { layout: 'padded' },
  args: {
    candidate,
    generatedAt: '2026-09-11T12:00:00Z',
    pinned: false,
  },
};

export default meta;
type Story = StoryObj<CleanupCandidateRow>;

export const Recommended: Story = {};

export const Kept: Story = {
  args: { pinned: true },
};

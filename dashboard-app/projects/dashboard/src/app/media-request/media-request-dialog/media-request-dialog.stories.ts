import { applicationConfig, type Meta, type StoryObj } from '@storybook/angular';

import { MEDIA_STACK_API } from '../../media-stack/media-stack-api';
import { MockMediaStackApi } from '../../media-stack/mock-media-stack-api';
import { MediaRequestDialog } from './media-request-dialog';

const meta: Meta<MediaRequestDialog> = {
  title: 'Media Request/Request Dialog',
  component: MediaRequestDialog,
  tags: ['autodocs'],
  decorators: [
    applicationConfig({
      providers: [{ provide: MEDIA_STACK_API, useClass: MockMediaStackApi }],
    }),
  ],
  args: {
    opened: true,
  },
};

export default meta;
type Story = StoryObj<MediaRequestDialog>;

export const MovieConfirmation: Story = {
  args: {
    item: {
      identity: 'movie:501001',
      type: 'movie',
      tmdbId: 501001,
      title: 'The Last Signal',
      year: 2026,
    },
  },
};

export const TvSeasonSelection: Story = {
  args: {
    item: {
      identity: 'tv:501005',
      type: 'tv',
      tmdbId: 501005,
      title: 'Harbor Lights',
      year: 2024,
    },
  },
};

import type { Meta, StoryObj } from '@storybook/angular';
import { MmAccordion } from './accordion';

const meta: Meta<MmAccordion> = {
  title: 'Primitives/Accordion',
  component: MmAccordion,
  tags: ['autodocs'],
  args: {
    items: [
      { id: '1', title: 'Quality profiles', content: 'HD-1080p and Remux tiers for movies and series.' },
      { id: '2', title: 'Indexers', content: 'Prowlarr syncs indexers to Sonarr and Radarr.' },
    ],
  },
};
export default meta;
type Story = StoryObj<MmAccordion>;

export const MultiOpen: Story = {};

export const SingleOpen: Story = {
  args: { singleOpen: true },
};

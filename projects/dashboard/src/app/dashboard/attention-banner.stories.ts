import { argsToTemplate, type Meta, type StoryObj } from '@storybook/angular';
import { AttentionBanner } from './attention-banner';

type BannerArgs = {
  headline: string;
  message: string;
};

const meta: Meta<BannerArgs> = {
  title: 'Dashboard/AttentionBanner',
  component: AttentionBanner,
  tags: ['autodocs'],
  argTypes: {
    headline: { control: 'text' },
    message: { control: 'text' },
  },
  args: {
    headline: '2 items need attention',
    message: 'SABnzbd is offline · Prowlarr is degraded',
  },
  render: (args) => ({
    props: args,
    template: `<mm-attention-banner ${argsToTemplate(args)} />`,
  }),
};

export default meta;
type Story = StoryObj<BannerArgs>;

export const Default: Story = {};

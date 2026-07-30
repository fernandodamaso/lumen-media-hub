import { argsToTemplate, type Meta, type StoryObj } from '@storybook/angular';
import { MetricCard } from './metric-card';

type MetricCardArgs = {
  iconName: 'folder' | 'download' | 'activity' | 'hard-drive';
  tone: 'premiere' | 'info' | 'success' | 'warning';
  label: string;
  value: string;
  meta: string | null;
  progress: number | null;
  href: string | null;
  external: boolean;
};

const meta: Meta<MetricCardArgs> = {
  title: 'Dashboard/MetricCard',
  component: MetricCard,
  tags: ['autodocs'],
  argTypes: {
    iconName: { control: 'select', options: ['folder', 'download', 'activity', 'hard-drive'] },
    tone: { control: 'select', options: ['premiere', 'info', 'success', 'warning'] },
    label: { control: 'text' },
    value: { control: 'text' },
    meta: { control: 'text' },
    progress: { control: { type: 'number', min: 0, max: 100, step: 1 } },
    href: { control: 'text' },
    external: { control: 'boolean' },
  },
  args: {
    iconName: 'folder',
    tone: 'premiere',
    label: 'Library',
    value: '504',
    meta: '428 movies · 76 series',
    progress: null,
    href: null,
    external: false,
  },
  render: (args) => ({
    props: args,
    template: `<div style="max-width:320px"><mm-metric-card ${argsToTemplate(args)} /></div>`,
  }),
};

export default meta;
type Story = StoryObj<MetricCardArgs>;

export const Library: Story = {};

export const Downloads: Story = {
  args: {
    iconName: 'download',
    tone: 'info',
    label: 'Downloads',
    value: '2',
    meta: 'Active downloads',
  },
};

export const Services: Story = {
  args: {
    iconName: 'activity',
    tone: 'success',
    label: 'Services',
    value: '6 / 8',
    meta: 'Healthy',
  },
};

export const Storage: Story = {
  args: {
    iconName: 'hard-drive',
    tone: 'warning',
    label: 'Storage',
    value: '78%',
    meta: '7.2 TB used · 1.8 TB free',
    progress: 78,
  },
};

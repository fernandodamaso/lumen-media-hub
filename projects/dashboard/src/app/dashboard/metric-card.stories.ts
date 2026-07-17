import { argsToTemplate, type Meta, type StoryObj } from '@storybook/angular';
import { MetricCard } from './metric-card';

type MetricCardArgs = {
  iconName: 'folder' | 'download' | 'activity' | 'hard-drive';
  iconBg: string;
  iconColor: string;
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
    iconBg: { control: 'color' },
    iconColor: { control: 'color' },
    label: { control: 'text' },
    value: { control: 'text' },
    meta: { control: 'text' },
    progress: { control: { type: 'range', min: 0, max: 100 } },
    href: { control: 'text' },
    external: { control: 'boolean' },
  },
  args: {
    iconName: 'folder',
    iconBg: 'rgba(104, 87, 245, 0.16)',
    iconColor: '#9b78ff',
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
    iconBg: 'rgba(94, 160, 255, 0.16)',
    iconColor: '#5ea0ff',
    label: 'Downloads',
    value: '2',
    meta: 'Active downloads',
  },
};

export const Services: Story = {
  args: {
    iconName: 'activity',
    iconBg: 'rgba(77, 220, 145, 0.16)',
    iconColor: '#4ddc91',
    label: 'Services',
    value: '6 / 8',
    meta: 'Healthy',
  },
};

export const Storage: Story = {
  args: {
    iconName: 'hard-drive',
    iconBg: 'rgba(244, 187, 67, 0.16)',
    iconColor: '#f4bb43',
    label: 'Storage',
    value: '78%',
    meta: '7.2 TB used · 1.8 TB free',
    progress: 78,
  },
};

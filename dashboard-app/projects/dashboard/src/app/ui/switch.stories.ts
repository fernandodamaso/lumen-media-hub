import type { Meta, StoryObj } from '@storybook/angular';
import { MmSwitch } from './switch';

const meta: Meta<MmSwitch> = { title: 'UI/Switch', component: MmSwitch, tags: ['autodocs'] };
export default meta;
type Story = StoryObj<MmSwitch>;

export const Off: Story = {
  render: (args) => ({
    props: { ...args, checked: false },
    template: '<mm-switch [(checked)]="checked">Auto-refresh</mm-switch>',
  }),
};

export const On: Story = {
  render: (args) => ({
    props: { ...args, checked: true },
    template: '<mm-switch [(checked)]="checked">Auto-refresh</mm-switch>',
  }),
};

export const Disabled: Story = {
  render: (args) => ({
    props: { ...args, checked: true },
    template: '<mm-switch [(checked)]="checked" [disabled]="true">Auto-refresh</mm-switch>',
  }),
};

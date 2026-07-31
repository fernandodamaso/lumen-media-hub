import type { Meta, StoryObj } from '@storybook/angular';
import { MmCheckbox } from './checkbox';

const meta: Meta<MmCheckbox> = { title: 'UI/Checkbox', component: MmCheckbox, tags: ['autodocs'] };
export default meta;
type Story = StoryObj<MmCheckbox>;

export const Unchecked: Story = {
  render: (args) => ({
    props: { ...args, checked: false },
    template: '<mm-checkbox [(checked)]="checked">Remember me</mm-checkbox>',
  }),
};

export const Checked: Story = {
  render: (args) => ({
    props: { ...args, checked: true },
    template: '<mm-checkbox [(checked)]="checked">Remember me</mm-checkbox>',
  }),
};

export const Disabled: Story = {
  render: (args) => ({
    props: { ...args, checked: false },
    template: '<mm-checkbox [(checked)]="checked" [disabled]="true">Remember me</mm-checkbox>',
  }),
};

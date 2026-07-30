import type { Meta, StoryObj } from '@storybook/angular';
import { MmSwitch } from './switch';
const meta: Meta<MmSwitch> = { title: 'UI/Switch', component: MmSwitch, tags: ['autodocs'] };
export default meta;
type Story = StoryObj<MmSwitch>;
export const Default: Story = { render: (args) => ({ props: args, template: '<mm-switch [checked]="checked">Auto-refresh</mm-switch>', args: { checked: true } }) };

import type { Meta, StoryObj } from '@storybook/angular';
import { MmCheckbox } from './checkbox';
const meta: Meta<MmCheckbox> = { title: 'UI/Checkbox', component: MmCheckbox, tags: ['autodocs'] };
export default meta;
type Story = StoryObj<MmCheckbox>;
export const Default: Story = { render: (args) => ({ props: args, template: '<mm-checkbox [checked]="checked">Remember me</mm-checkbox>' }) };

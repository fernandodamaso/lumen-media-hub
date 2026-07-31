import type { Meta, StoryObj } from '@storybook/angular';
import { MmSeparator } from './separator';
const meta: Meta<MmSeparator> = { title: 'UI/Separator', component: MmSeparator, tags: ['autodocs'] };
export default meta;
type Story = StoryObj<MmSeparator>;
export const Default: Story = { args: { label: 'or' } };

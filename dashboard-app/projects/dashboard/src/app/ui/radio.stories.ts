import type { Meta, StoryObj } from '@storybook/angular';
import { MmRadio } from './radio';
const meta: Meta<MmRadio> = { title: 'UI/Radio', component: MmRadio, tags: ['autodocs'] };
export default meta;
type Story = StoryObj<MmRadio>;
export const Default: Story = { args: { name: 'quality', value: '1080p', checked: true }, render: (args) => ({ props: args, template: '<mm-radio [name]="name" [value]="value" [checked]="checked">1080p WEB-DL</mm-radio>' }) };

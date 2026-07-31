import type { Meta, StoryObj } from '@storybook/angular';
import { MmRadio } from './radio';

const meta: Meta<MmRadio> = { title: 'UI/Radio', component: MmRadio, tags: ['autodocs'] };
export default meta;
type Story = StoryObj<MmRadio>;

export const Group: Story = {
  render: () => ({
    props: { quality: '1080p' },
    template: `
      <div style="display:flex;flex-direction:column;gap:12px">
        <mm-radio name="quality" value="720p" [checked]="quality === '720p'" (valueSelect)="quality = $event">720p HDTV</mm-radio>
        <mm-radio name="quality" value="1080p" [checked]="quality === '1080p'" (valueSelect)="quality = $event">1080p WEB-DL</mm-radio>
        <mm-radio name="quality" value="2160p" [checked]="quality === '2160p'" (valueSelect)="quality = $event">2160p Remux</mm-radio>
      </div>
    `,
  }),
};

export const Disabled: Story = {
  args: { name: 'quality', value: '1080p', checked: false, disabled: true },
  render: (args) => ({
    props: args,
    template: '<mm-radio [name]="name" [value]="value" [(checked)]="checked" [disabled]="disabled">1080p WEB-DL</mm-radio>',
  }),
};

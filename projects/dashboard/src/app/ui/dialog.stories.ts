import { argsToTemplate, type Meta, type StoryObj } from '@storybook/angular';
import { MmButton, MmDialog, type MmDialogTone } from './index';

type DialogArgs = {
  title: string;
  tone: MmDialogTone;
};

const meta: Meta<DialogArgs> = {
  title: 'UI/Dialog',
  component: MmDialog,
  tags: ['autodocs'],
  argTypes: {
    title: { control: 'text' },
    tone: {
      control: 'select',
      options: ['default', 'warning', 'danger'],
    },
  },
  args: {
    title: 'Service details',
    tone: 'default',
  },
  render: (args) => ({
    props: args,
    moduleMetadata: {
      imports: [MmButton, MmDialog],
    },
    template: `
      <mm-button label="Open dialog" (click)="dlg.open()" />
      <mm-dialog #dlg ${argsToTemplate(args)}>
        <p style="margin:0;color:var(--mm-component-text-secondary);font-size:13px;line-height:1.5">
          Modal body content for reviewing a connected service.
        </p>
        <div mmDialogFooter>
          <mm-button label="Done" variant="quiet" (click)="dlg.close()" />
        </div>
      </mm-dialog>
    `,
  }),
};

export default meta;
type Story = StoryObj<DialogArgs>;

export const Default: Story = {};

export const Warning: Story = {
  args: { title: 'Prowlarr — Degraded', tone: 'warning' },
};

export const Danger: Story = {
  args: { title: 'SABnzbd — Down', tone: 'danger' },
};

export const OpensOnTrigger: Story = {
  args: { title: 'Opened dialog', tone: 'default' },
  play: ({ canvasElement }) => {
    const trigger = canvasElement.querySelector<HTMLButtonElement>('mm-button button, button');
    if (!trigger) throw new Error('Trigger button was not rendered');
    trigger.click();
    const dialog = canvasElement.querySelector<HTMLDialogElement>('dialog');
    if (!dialog?.open) throw new Error('Dialog did not open');
  },
};

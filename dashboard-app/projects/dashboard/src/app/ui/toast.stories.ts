import type { Meta, StoryObj } from '@storybook/angular';
import { MmToast, MmToastHost } from './toast';
import { MmToastService } from './toast.service';

const meta: Meta = {
  title: 'Primitives/Toast',
  component: MmToast,
  tags: ['autodocs'],
  render: () => ({
    template: `<mm-toast-host />`,
    applicationConfig: {
      providers: [MmToastService],
    },
    moduleMetadata: { imports: [MmToastHost] },
    props: {
      fire: (svc: MmToastService) => {
        svc.show('Request sent', { body: 'Jellyseerr will notify when approved.', tone: 'gold' });
      },
    },
  }),
};
export default meta;
type Story = StoryObj;

export const Host: Story = {};

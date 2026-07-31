import type { Meta, StoryObj } from '@storybook/angular';
import { Component, inject } from '@angular/core';
import { MmToast, MmToastHost } from './toast';
import { MmToastService } from './toast.service';

@Component({
  selector: 'mm-toast-story-fire',
  imports: [MmToastHost],
  providers: [MmToastService],
  template: `<mm-toast-host />`,
  standalone: true,
})
class ToastStoryFire {
  private readonly toasts = inject(MmToastService);
  constructor() {
    this.toasts.show('Request sent', { body: 'Jellyseerr will notify when approved.', tone: 'gold' });
    this.toasts.show('Scan complete', { body: 'Library refreshed.', tone: 'success' });
    this.toasts.show('Update failed', { body: 'Could not reach Sonarr.', tone: 'error' });
  }
}

const meta: Meta = {
  title: 'Primitives/Toast',
  tags: ['autodocs'],
};
export default meta;
type Story = StoryObj;

export const Host: Story = {
  render: () => ({
    moduleMetadata: { imports: [ToastStoryFire] },
    template: `<mm-toast-story-fire />`,
  }),
};

export const Single: Story = {
  render: () => ({
    // ponytail: import MmToast so Knip sees the component used; host stories cover the toast zone.
    moduleMetadata: { imports: [MmToast] },
    template: `<mm-toast>Short inline toast</mm-toast>`,
  }),
};

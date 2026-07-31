import type { Meta, StoryObj } from '@storybook/angular';
import { MmAvatar, MmAvatarStack } from './avatar';

const POSTER_SVG =
  'data:image/svg+xml,' +
  encodeURIComponent(
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 56 56"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#8b7cf6"/><stop offset="1" stop-color="#d4a94e"/></linearGradient></defs><rect width="56" height="56" fill="url(#g)"/><circle cx="28" cy="22" r="9" fill="#0a0a0f" opacity=".55"/><ellipse cx="28" cy="46" rx="14" ry="9" fill="#0a0a0f" opacity=".55"/></svg>',
  );

const meta: Meta<MmAvatar> = {
  title: 'Primitives/Avatar',
  component: MmAvatar,
  tags: ['autodocs'],
};
export default meta;
type Story = StoryObj<MmAvatar>;

export const Default: Story = { args: { initials: 'M', label: 'Media' } };
export const Gold: Story = { args: { initials: 'G', tone: 'gold' } };
export const TwoLetters: Story = { args: { initials: 'FE', label: 'Fernanda' } };
export const Image: Story = { args: { src: POSTER_SVG, label: 'Fernanda' } };
export const ImageFallback: Story = {
  name: 'Image (broken URL falls back to initials)',
  args: { src: 'https://invalid.example/avatar.png', initials: 'FE', label: 'Fernanda' },
};
export const IconUser: Story = { args: { icon: 'user', label: 'Account' } };
export const IconFilm: Story = { args: { icon: 'film', tone: 'violet', label: 'Movie' } };

export const Sizes: Story = {
  render: () => ({
    props: { poster: POSTER_SVG },
    template: `
      <div style="display:flex;align-items:center;gap:14px">
        <mm-avatar size="sm" initials="FE" />
        <mm-avatar size="md" initials="FE" />
        <mm-avatar size="lg" initials="FE" />
        <mm-avatar size="lg" [src]="poster" />
        <mm-avatar size="lg" icon="user" tone="gold" />
      </div>
    `,
    moduleMetadata: { imports: [MmAvatar] },
  }),
};

export const Stack: Story = {
  render: () => ({
    props: { poster: POSTER_SVG },
    template: `
      <mm-avatar-stack>
        <mm-avatar [src]="poster" label="Fernanda" />
        <mm-avatar initials="FE" tone="gold" />
        <mm-avatar icon="user" tone="violet" />
        <mm-avatar initials="C" tone="green" />
      </mm-avatar-stack>
    `,
    moduleMetadata: { imports: [MmAvatar, MmAvatarStack] },
  }),
};

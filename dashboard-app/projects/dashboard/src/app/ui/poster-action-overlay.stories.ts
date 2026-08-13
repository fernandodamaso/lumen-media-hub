import { type Meta, type StoryObj } from '@storybook/angular';
import { LucideEye, LucidePlay, LucideTrash2 } from '@lucide/angular';
import { MOCK_POSTER, mockArtUrl } from '../../testing/storybook-mock-art';
import { MmIconButton, MmMediaCard, MmPosterActionOverlay } from './index';

const meta: Meta = {
  title: 'UI/PosterActionOverlay',
  component: MmPosterActionOverlay,
  tags: ['autodocs'],
};

export default meta;
type Story = StoryObj;

export const LibraryActions: Story = {
  render: () => ({
    moduleMetadata: {
      imports: [MmPosterActionOverlay, MmMediaCard, MmIconButton, LucidePlay, LucideEye, LucideTrash2],
    },
    template: `<div style="max-width:220px">
      <mm-poster-action-overlay ariaLabel="Actions for Moonrise">
        <mm-media-card
          title="Moonrise"
          subtitle="2024 · Movie"
          captionPlacement="none"
          [imageUrl]="'${MOCK_POSTER.movie2}'"
          [art]="'${mockArtUrl(MOCK_POSTER.movie2)}'"
        />
        <mm-icon-button label="Play Moonrise" href="https://jellyfin.example/item" surface="overlay">
          <svg lucidePlay [size]="16" [strokeWidth]="2.2" aria-hidden="true"></svg>
        </mm-icon-button>
        <mm-icon-button label="Mark watched" surface="overlay">
          <svg lucideEye [size]="16" [strokeWidth]="2.2" aria-hidden="true"></svg>
        </mm-icon-button>
        <mm-icon-button label="Delete" surface="overlay">
          <svg lucideTrash2 [size]="16" [strokeWidth]="2.2" aria-hidden="true"></svg>
        </mm-icon-button>
      </mm-poster-action-overlay>
    </div>`,
  }),
  play: ({ canvasElement }) => {
    if (!canvasElement.querySelector('.mm-poster-action-overlay__actions')) {
      throw new Error('PosterActionOverlay story is missing the action group');
    }
    if (!canvasElement.querySelector('a.mm-icon-button--overlay[aria-label="Play Moonrise"]')) {
      throw new Error('PosterActionOverlay story is missing the overlay Play link');
    }
    const buttons = canvasElement.querySelectorAll('.mm-poster-action-overlay__actions .mm-icon-button--overlay');
    if (buttons.length !== 3) {
      throw new Error(`Expected 3 overlay actions, found ${buttons.length}`);
    }
  },
};

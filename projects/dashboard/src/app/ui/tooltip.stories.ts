import { argsToTemplate, type Meta, type StoryObj } from '@storybook/angular';
import { LucidePlay, LucideRefreshCw, LucideSearch } from '@lucide/angular';
import { MmButton, MmTooltip, type MmTooltipPlacement, type MmTooltipTone } from './index';

type TooltipArgs = {
  text: string;
  placement: MmTooltipPlacement;
  tone: MmTooltipTone;
};

const meta: Meta<TooltipArgs> = {
  title: 'UI/Tooltip',
  component: MmTooltip,
  tags: ['autodocs'],
  parameters: {
    docs: {
      description: {
        component:
          'Hover/focus tip for icon-only controls. Keep the accessible name on the trigger; use a short tip label here.',
      },
    },
  },
  argTypes: {
    text: { control: 'text' },
    placement: { control: 'select', options: ['top', 'bottom'] },
    tone: { control: 'select', options: ['default', 'accent'] },
  },
  args: {
    text: 'Refresh metadata',
    placement: 'top',
    tone: 'default',
  },
  render: (args) => ({
    props: args,
    moduleMetadata: { imports: [MmButton, MmTooltip] },
    template: `<div style="padding:48px;display:flex;justify-content:center">
      <mm-tooltip ${argsToTemplate(args)}>
        <mm-button label="Hover me" variant="quiet" />
      </mm-tooltip>
    </div>`,
  }),
};

export default meta;
type Story = StoryObj<TooltipArgs>;

export const Default: Story = {};

export const Accent: Story = {
  args: { text: 'Play in Jellyfin', tone: 'accent' },
};

export const Bottom: Story = {
  args: { text: 'Opens Discover search', placement: 'bottom' },
};

/** Both tip styles used across the product. */
export const Tones: Story = {
  render: () => ({
    moduleMetadata: { imports: [MmButton, MmTooltip] },
    template: `<div style="display:flex;gap:28px;justify-content:center;padding:56px 24px">
      <mm-tooltip text="Default tip" tone="default">
        <mm-button label="Default" variant="quiet" />
      </mm-tooltip>
      <mm-tooltip text="Accent tip" tone="accent">
        <mm-button label="Accent" variant="quiet" />
      </mm-tooltip>
    </div>`,
  }),
  play: ({ canvasElement }) => {
    const tips = canvasElement.querySelectorAll('mm-tooltip');
    if (tips.length !== 2) throw new Error(`Expected 2 tooltips, found ${tips.length}`);
    if (!tips[0].classList.contains('mm-tooltip')) {
      throw new Error('Default tooltip missing host class');
    }
    if (!tips[1].classList.contains('mm-tooltip--accent')) {
      throw new Error('Accent tooltip missing tone class');
    }
  },
};

export const PosterActions: Story = {
  render: () => ({
    moduleMetadata: { imports: [MmTooltip, LucidePlay, LucideRefreshCw, LucideSearch] },
    template: `<div style="padding:64px 24px;display:flex;justify-content:center;gap:8px;background:var(--mm-component-muted-bg);border-radius:12px">
      <mm-tooltip text="Play" tone="accent">
        <button type="button" aria-label="Play title" style="width:30px;height:30px;border-radius:8px;border:1px solid var(--mm-component-border);background:var(--mm-component-card-bg);color:var(--mm-component-text-primary);display:grid;place-items:center;cursor:pointer">
          <svg lucidePlay [size]="14" aria-hidden="true"></svg>
        </button>
      </mm-tooltip>
      <mm-tooltip text="Refresh">
        <button type="button" aria-label="Refresh metadata" style="width:30px;height:30px;border-radius:8px;border:1px solid var(--mm-component-border);background:var(--mm-component-card-bg);color:var(--mm-component-text-primary);display:grid;place-items:center;cursor:pointer">
          <svg lucideRefreshCw [size]="14" aria-hidden="true"></svg>
        </button>
      </mm-tooltip>
      <mm-tooltip text="Search">
        <button type="button" aria-label="Search releases" style="width:30px;height:30px;border-radius:8px;border:1px solid var(--mm-component-border);background:var(--mm-component-card-bg);color:var(--mm-component-text-primary);display:grid;place-items:center;cursor:pointer">
          <svg lucideSearch [size]="14" aria-hidden="true"></svg>
        </button>
      </mm-tooltip>
    </div>`,
  }),
  play: ({ canvasElement }) => {
    const bubbles = [...canvasElement.querySelectorAll('.mm-tooltip__bubble')].map((el) => el.textContent.trim());
    if (!bubbles.includes('Play') || !bubbles.includes('Refresh') || !bubbles.includes('Search')) {
      throw new Error(`Poster action tips missing: ${bubbles.join(', ')}`);
    }
  },
};

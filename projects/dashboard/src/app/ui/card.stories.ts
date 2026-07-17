import { argsToTemplate, type Meta, type StoryObj } from '@storybook/angular';
import { MmButton, MmCard } from './index';

type CardArgs = {
  labelledBy: string;
};

const meta: Meta<CardArgs> = {
  title: 'UI/Card',
  component: MmCard,
  tags: ['autodocs'],
  argTypes: {
    labelledBy: { control: 'text' },
  },
  args: {
    labelledBy: 'card-heading',
  },
  render: (args) => ({
    props: args,
    moduleMetadata: { imports: [MmCard, MmButton] },
    template: `<div style="max-width:420px;height:280px">
      <mm-card ${argsToTemplate(args)}>
        <h2 mm-card-header id="card-heading">Downloads</h2>
        <mm-button mm-card-header-actions label="Refresh" variant="quiet" />
        <p>Active transfers and queue health for the current Demo session.</p>
        <span mm-card-footer>Updated just now</span>
        <mm-button mm-card-footer-actions label="Open" variant="quiet" />
      </mm-card>
    </div>`,
  }),
};

export default meta;
type Story = StoryObj<CardArgs>;

export const Default: Story = {
  play: async ({ canvasElement }) => {
    const card = canvasElement.querySelector('.mm-card');
    if (!card) throw new Error('Card was not rendered');
    if (card.getAttribute('aria-labelledby') !== 'card-heading') {
      throw new Error('Card is missing its labelledBy association');
    }
    const refresh = canvasElement.querySelector<HTMLButtonElement>('button');
    if (!refresh || refresh.textContent?.trim() !== 'Refresh') {
      throw new Error('Card header action was not rendered');
    }
    refresh.focus({ focusVisible: true });
    if (document.activeElement !== refresh) throw new Error('Card action did not receive focus');
    const outline = getComputedStyle(refresh);
    if (outline.outlineStyle === 'none' || Number.parseFloat(outline.outlineWidth) <= 0) {
      throw new Error('Card action focus ring is not visible');
    }
  },
};

export const BodyOnly: Story = {
  args: { labelledBy: '' },
  render: () => ({
    moduleMetadata: { imports: [MmCard] },
    template: `<div style="max-width:420px">
      <mm-card>
        <p>A minimal card with content only — header and footer stay hidden when empty.</p>
      </mm-card>
    </div>`,
  }),
  play: async ({ canvasElement }) => {
    const body = canvasElement.querySelector('.mm-card__body');
    if (!body?.textContent?.includes('minimal card')) {
      throw new Error('Body-only card content was not rendered');
    }
    if (canvasElement.querySelector('[mm-card-header], [mm-card-footer]')) {
      throw new Error('Body-only card should not project header or footer content');
    }
  },
};

import { argsToTemplate, type Meta, type StoryObj } from '@storybook/angular';
import { MmButton, MmStateCard, type MmStateCardKind } from './index';

type StateCardArgs = {
  kind: MmStateCardKind;
  tone: 'default' | 'danger';
  title: string;
  message: string;
  centered: boolean;
};

const meta: Meta<StateCardArgs> = {
  title: 'UI/StateCard',
  component: MmStateCard,
  tags: ['autodocs'],
  argTypes: {
    kind: {
      control: 'select',
      options: ['loading', 'empty', 'error'],
    },
    tone: {
      control: 'select',
      options: ['default', 'danger'],
    },
    title: { control: 'text' },
    message: { control: 'text' },
    centered: { control: 'boolean' },
  },
  args: {
    kind: 'empty',
    tone: 'default',
    title: 'Nothing here yet',
    message: 'There is no content to show right now.',
    centered: false,
  },
  render: (args) => ({
    props: args,
    template: `<div style="max-width:320px"><mm-state-card ${argsToTemplate(args)} /></div>`,
  }),
};

export default meta;
type Story = StoryObj<StateCardArgs>;

export const Empty: Story = {};

export const CenteredEmpty: Story = {
  args: {
    kind: 'empty',
    centered: true,
    title: 'No active downloads',
    message: 'Your queue is clear. New downloads will appear here.',
  },
};

export const Loading: Story = {
  args: {
    kind: 'loading',
    title: 'Loading',
    message: 'Fetching media',
  },
};

export const ErrorState: Story = {
  args: {
    kind: 'error',
    tone: 'danger',
    title: 'Error',
    message: 'Try again',
  },
  render: (args) => ({
    props: args,
    moduleMetadata: { imports: [MmStateCard, MmButton] },
    template: `<div style="max-width:320px">
      <mm-state-card ${argsToTemplate(args)}>
        <mm-button label="Retry" />
      </mm-state-card>
    </div>`,
  }),
  play: ({ canvasElement }) => {
    if (!canvasElement.querySelector('.mm-state-card--danger')) {
      throw new Error('Error state card is missing its danger tone');
    }
    const retry = [...canvasElement.querySelectorAll('button')].find(
      (button) => button.textContent.trim() === 'Retry',
    );
    if (!retry) throw new Error('Retry action was not rendered on the error state card');
    retry.focus({ focusVisible: true });
    if (document.activeElement !== retry) throw new Error('Retry action did not receive focus');
    const outline = getComputedStyle(retry);
    if (outline.outlineStyle === 'none' || Number.parseFloat(outline.outlineWidth) <= 0) {
      throw new Error('Retry action focus ring is not visible');
    }
  },
};

export const States: Story = {
  render: () => ({
    moduleMetadata: { imports: [MmStateCard, MmButton] },
    template: `<div style="display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;max-width:900px">
      <mm-state-card kind="loading" title="Loading" message="Fetching media" />
      <mm-state-card kind="empty" title="Empty" message="Nothing has been added" />
      <mm-state-card tone="danger" kind="error" title="Error" message="Try again">
        <mm-button label="Retry" />
      </mm-state-card>
    </div>`,
  }),
  play: ({ canvasElement }) => {
    const cards = canvasElement.querySelectorAll('.mm-state-card');
    if (cards.length !== 3) throw new Error(`Expected 3 state cards, found ${cards.length}`);
    if (!canvasElement.querySelector('.mm-state-card--danger')) {
      throw new Error('Error state card is missing its danger tone');
    }
    const retry = [...canvasElement.querySelectorAll('button')].find(
      (button) => button.textContent.trim() === 'Retry',
    );
    if (!retry) throw new Error('Retry action was not rendered on the error state card');
    retry.focus({ focusVisible: true });
    if (document.activeElement !== retry) throw new Error('Retry action did not receive focus');
    const outline = getComputedStyle(retry);
    if (outline.outlineStyle === 'none' || Number.parseFloat(outline.outlineWidth) <= 0) {
      throw new Error('Retry action focus ring is not visible');
    }
  },
};

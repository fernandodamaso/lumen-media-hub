import type { Meta, StoryObj } from '@storybook/angular';
import { MmTabPanel, MmTabs } from './tabs';

const meta: Meta<MmTabs> = {
  title: 'Primitives/Tabs',
  component: MmTabs,
  tags: ['autodocs'],
  args: {
    tabs: [
      { id: 'movies', label: 'Movies' },
      { id: 'shows', label: 'Shows' },
      { id: 'people', label: 'People' },
    ],
    active: 'movies',
  },
};
export default meta;
type Story = StoryObj<MmTabs>;

export const Default: Story = {
  render: (args) => ({
    props: args,
    moduleMetadata: { imports: [MmTabPanel] },
    template: `
      <mm-tabs [tabs]="tabs" [(active)]="active">
        <mm-tab-panel panelId="movies">Movies panel content.</mm-tab-panel>
        <mm-tab-panel panelId="shows">Shows panel content.</mm-tab-panel>
        <mm-tab-panel panelId="people">People panel content.</mm-tab-panel>
      </mm-tabs>
    `,
  }),
};

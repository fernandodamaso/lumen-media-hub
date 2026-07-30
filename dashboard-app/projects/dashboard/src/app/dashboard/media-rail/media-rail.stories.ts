import { provideRouter } from '@angular/router';
import { applicationConfig, type Meta, type StoryObj } from '@storybook/angular';
import { MediaRail } from './media-rail';

const meta: Meta = {
  title: 'Dashboard/MediaRail',
  component: MediaRail,
  tags: ['autodocs'],
  decorators: [applicationConfig({ providers: [provideRouter([])] })],
  render: () => ({
    template: `
      <mm-media-rail title="Continue Watching" count="4 in progress" linkTo="/library" linkLabel="View all">
        @for (title of titles; track title) {
          <div style="flex:0 0 272px;aspect-ratio:16/10;border-radius:16px;border:1px solid var(--mm-component-border);
                      background:linear-gradient(145deg,#26243a,#101018);display:grid;place-items:center;
                      font-family:var(--mm-font-display,'Fraunces',Georgia,serif);font-size:18px">
            {{ title }}
          </div>
        }
      </mm-media-rail>
    `,
    props: { titles: ['Ashes of the Crown', 'Neon Veil', 'The Shōgun Court', 'After Us'] },
  }),
};
export default meta;
type Story = StoryObj;

export const Default: Story = {};

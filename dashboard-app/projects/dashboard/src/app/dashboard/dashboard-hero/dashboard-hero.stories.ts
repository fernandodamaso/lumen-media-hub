import { signal } from '@angular/core';
import { provideRouter } from '@angular/router';
import { applicationConfig, type Meta, type StoryObj } from '@storybook/angular';
import { HeroFacade, HeroView } from './hero.facade';
import { DashboardHero } from './dashboard-hero';

const view: HeroView = {
  id: 'id-1',
  kind: 'movie',
  title: 'Ashes of the Crown',
  titleParts: { head: 'Ashes of the', tail: 'Crown' },
  kicker: 'Featured',
  backdropUrl: '',
  meta: ['2026', '★ 8.4', '2h 46m', 'Fantasy, Adventure'],
  overview: 'A deposed queen crosses the burned wastes to raise an army against the dragon that destroyed her house.',
  progressPercent: 52,
  remainingLabel: '1h 21m remaining',
  playHref: 'http://jf/web/index.html#!/details?id=id-1',
};

const meta: Meta = {
  title: 'Dashboard/Hero',
  component: DashboardHero,
  tags: ['autodocs'],
};
export default meta;
type Story = StoryObj;

export const Default: Story = {
  decorators: [applicationConfig({ providers: [provideRouter([]), { provide: HeroFacade, useValue: { view: signal(view) } }] })],
};

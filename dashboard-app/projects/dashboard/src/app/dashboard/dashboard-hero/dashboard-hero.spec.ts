import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { fixtureHost } from '../../../testing/fixture-host';
import { HeroFacade, HeroView } from './hero.facade';
import { DashboardHero } from './dashboard-hero';

const heroView: HeroView = {
  id: 'id-1',
  kind: 'movie',
  title: 'Ashes of the Crown',
  titleParts: { head: 'Ashes of the', tail: 'Crown' },
  kicker: 'Featured',
  backdropUrl: 'http://jf/Items/id-1/Images/Backdrop',
  meta: ['2026', '★ 8.4', '2h 46m', 'Fantasy, Adventure'],
  overview: 'A deposed queen crosses the burned wastes.',
  progressPercent: 52,
  remainingLabel: '1h 21m remaining',
  playHref: 'http://jf/web/index.html#!/details?id=id-1',
};

describe('DashboardHero', () => {
  const view = signal<HeroView | null>(null);

  beforeEach(() => {
    view.set(null);
    TestBed.configureTestingModule({
      imports: [DashboardHero],
      providers: [provideRouter([]), { provide: HeroFacade, useValue: { view } }],
    });
  });

  it('renders nothing when no candidate qualifies', () => {
    const fixture = TestBed.createComponent(DashboardHero);
    fixture.detectChanges();
    expect(fixtureHost(fixture).querySelector('.hero')).toBeNull();
  });

  it('renders kicker, backdrop, gold-italic last word, meta, and actions', () => {
    view.set(heroView);
    const fixture = TestBed.createComponent(DashboardHero);
    fixture.detectChanges();
    const root = fixtureHost(fixture);

    expect(root.querySelector('.hero__kicker')?.textContent).toContain('Featured');
    expect(root.querySelector<HTMLElement>('.hero__bg')?.style.background).toContain(
      `url("${heroView.backdropUrl}")`,
    );

    const heading = root.querySelector('h1');
    expect(heading?.textContent).toContain('Ashes of the');
    expect(heading?.querySelector('em')?.textContent).toBe('Crown');

    const meta = root.querySelector('.hero__meta')?.textContent ?? '';
    for (const segment of heroView.meta) expect(meta).toContain(segment);
    expect(root.querySelector('.hero__overview')?.textContent).toContain('deposed queen');

    const play = root.querySelector('[data-testid="hero-play"]');
    expect(play?.getAttribute('href')).toBe(heroView.playHref);
    expect(play?.textContent).toContain('Play');
    expect(root.querySelector('[data-testid="hero-details"]')?.getAttribute('href')).toBe('/library');

    expect(root.querySelector('[role="progressbar"]')?.getAttribute('aria-valuenow')).toBe('52');
    expect(root.querySelector('.hero__prog')?.textContent).toContain('1h 21m remaining');
  });

  it('hides the progress row when nothing has been watched', () => {
    view.set({ ...heroView, progressPercent: 0, remainingLabel: '' });
    const fixture = TestBed.createComponent(DashboardHero);
    fixture.detectChanges();
    expect(fixtureHost(fixture).querySelector('.hero__prog')).toBeNull();
  });
});

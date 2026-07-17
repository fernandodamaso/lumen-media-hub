import { ComponentFixture, TestBed } from '@angular/core/testing';
import { computed, signal } from '@angular/core';
import { groupCalendarEvents } from './calendar-format';
import { vi } from 'vitest';
import { CalendarBoard } from './calendar-board';
import { CalendarFacade, CalendarRailEvent, CalendarStatus } from './calendar.facade';

describe('CalendarBoard', () => {
  let fixture: ComponentFixture<CalendarBoard>;
  let facade: ReturnType<typeof createFacade>;

  beforeEach(() => {
    facade = createFacade();
    TestBed.configureTestingModule({
      imports: [CalendarBoard],
      providers: [{ provide: CalendarFacade, useValue: facade }],
    });
    fixture = TestBed.createComponent(CalendarBoard);
  });

  it('renders loading, empty, and error states with retry recovery', async () => {
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelectorAll('.cal-skeleton__row').length).toBeGreaterThan(0);

    facade.status.set('empty');
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Nothing upcoming');

    facade.status.set('error');
    facade.error.set('Offline');
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Offline');
    findButton('Try again').click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(facade.refresh).toHaveBeenCalled();
    expect(facade.status()).toBe('ready');
  });

  it('renders mixed events with links only for known library mappings', () => {
    facade.status.set('ready');
    facade.events.set([
      {
        id: '1',
        time: 'Jul 12',
        kind: 'episode',
        title: 'Cowboy Bebop',
        subtitle: 'S1 E5',
        status: 'pending',
        airDate: '2026-07-12T18:00:00Z',
        href: 'http://localhost:8989/series/cowboy-bebop',
      },
      {
        id: '2',
        time: 'Jul 13',
        kind: 'movie',
        title: 'Dune',
        subtitle: 'Theatrical',
        status: 'available',
        airDate: '2026-07-13T00:00:00Z',
        href: 'http://localhost:7878/movie/dune-2021',
      },
      {
        id: '3',
        time: 'Jul 15',
        kind: 'movie',
        title: 'Night Transit',
        subtitle: 'Premiere',
        status: 'pending',
        airDate: '2026-07-15T12:00:00Z',
        href: null,
      },
    ]);
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Cowboy Bebop');
    expect(text).toContain('Episode');
    expect(text).toContain('Movie');
    expect(text).toContain('Available');

    const links = Array.from(fixture.nativeElement.querySelectorAll('a.cal-link')) as HTMLAnchorElement[];
    expect(links).toHaveLength(2);
    expect(links[0].getAttribute('href')).toBe('http://localhost:8989/series/cowboy-bebop');
    expect(links[0].getAttribute('target')).toBe('_blank');
    expect(links[0].getAttribute('rel')).toBe('noreferrer');
    expect(links[1].getAttribute('href')).toBe('http://localhost:7878/movie/dune-2021');

    const unmatched = Array.from(fixture.nativeElement.querySelectorAll('.cal-title')) as HTMLElement[];
    const night = unmatched.find((node) => node.textContent?.includes('Night Transit'));
    expect(night?.tagName.toLowerCase()).toBe('span');
    expect(fixture.nativeElement.querySelector('.cal-list')?.getAttribute('aria-live')).toBe('polite');
  });

  it('declares container-query compact layout for narrow dashboard rail', () => {
    fixture.detectChanges();
    const styles = componentStyles();
    expect(styles).toContain('@container (max-width: 420px)');
    expect(styles).toMatch(/@container \(max-width: 420px\)[\s\S]*\.cal-row[\s\S]*gap:\s*10px/);
  });

  function findButton(label: string): HTMLButtonElement {
    return (Array.from(fixture.nativeElement.querySelectorAll('button')) as HTMLButtonElement[]).find(
      (button) => button.textContent?.includes(label),
    ) as HTMLButtonElement;
  }
});

function createFacade() {
  const status = signal<CalendarStatus>('loading');
  const events = signal<CalendarRailEvent[]>([]);
  const error = signal('');
  const refresh = vi.fn(async () => status.set('ready'));
  return {
    status,
    events,
    error,
    startPolling: vi.fn(),
    refresh,
    groups: computed(() => groupCalendarEvents(events())),
  };
}

function componentStyles(): string {
  return Array.from(document.querySelectorAll('style'))
    .map((node) => node.textContent ?? '')
    .join('\n');
}

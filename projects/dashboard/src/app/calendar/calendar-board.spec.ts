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
    const now = new Date();
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, '0');
    const d0 = String(now.getDate()).padStart(2, '0');
    const d1Date = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1);
    const d2Date = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 2);
    const d1 = `${d1Date.getFullYear()}-${String(d1Date.getMonth() + 1).padStart(2, '0')}-${String(d1Date.getDate()).padStart(2, '0')}`;
    const d2 = `${d2Date.getFullYear()}-${String(d2Date.getMonth() + 1).padStart(2, '0')}-${String(d2Date.getDate()).padStart(2, '0')}`;

    facade.status.set('ready');
    facade.events.set([
      {
        id: '1',
        time: '18:00',
        kind: 'episode',
        title: 'Cowboy Bebop',
        subtitle: 'S1 E5',
        status: 'pending',
        airDate: `${y}-${m}-${d0}T18:00:00`,
        href: 'http://localhost:8989/series/cowboy-bebop',
      },
      {
        id: '2',
        time: '00:00',
        kind: 'movie',
        title: 'Dune',
        subtitle: 'Theatrical',
        status: 'available',
        airDate: `${d1}T00:00:00`,
        href: 'http://localhost:7878/movie/dune-2021',
      },
      {
        id: '3',
        time: '12:00',
        kind: 'movie',
        title: 'Night Transit',
        subtitle: 'Premiere',
        status: 'pending',
        airDate: `${d2}T12:00:00`,
        href: null,
      },
    ]);
    fixture.detectChanges();

    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Cowboy Bebop');
    expect(text).toContain('Episode');
    expect(text).toContain('Movie');
    expect(text).toContain('TODAY');
    expect(text).toContain('TOMORROW');

    const links: HTMLAnchorElement[] = Array.from(fixture.nativeElement.querySelectorAll('a.cal-link'));
    expect(links).toHaveLength(2);
    expect(links[0].getAttribute('href')).toBe('http://localhost:8989/series/cowboy-bebop');
    expect(links[0].getAttribute('target')).toBe('_blank');
    expect(links[0].getAttribute('rel')).toBe('noreferrer');
    expect(links[1].getAttribute('href')).toBe('http://localhost:7878/movie/dune-2021');

    const unmatched: HTMLElement[] = Array.from(fixture.nativeElement.querySelectorAll('.cal-title'));
    const night = unmatched.find((node) => node.textContent.includes('Night Transit'));
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
    const buttons: HTMLButtonElement[] = Array.from(fixture.nativeElement.querySelectorAll('button'));
    const match = buttons.find((button) => button.textContent.includes(label));
    if (!match) throw new Error(`Button not found: ${label}`);
    return match;
  }
});

function createFacade() {
  const status = signal<CalendarStatus>('loading');
  const events = signal<CalendarRailEvent[]>([]);
  const error = signal('');
  const refresh = vi.fn(() => { status.set('ready'); return Promise.resolve(); });
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
    .map((node) => node.textContent)
    .join('\n');
}

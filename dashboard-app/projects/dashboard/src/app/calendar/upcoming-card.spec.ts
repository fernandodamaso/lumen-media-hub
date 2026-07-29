import { ComponentFixture, TestBed } from '@angular/core/testing';
import { computed, signal } from '@angular/core';
import { groupCalendarEvents } from './calendar-format';
import { vi } from 'vitest';
import { fixtureHost } from '../../testing/fixture-host';
import { UpcomingCard } from './upcoming-card';
import { CalendarFacade, CalendarRailEvent, CalendarStatus } from './calendar.facade';

describe('UpcomingCard', () => {
  let fixture: ComponentFixture<UpcomingCard>;
  let facade: ReturnType<typeof createFacade>;

  beforeEach(() => {
    facade = createFacade();
    TestBed.configureTestingModule({
      imports: [UpcomingCard],
      providers: [{ provide: CalendarFacade, useValue: facade }],
    });
    fixture = TestBed.createComponent(UpcomingCard);
  });

  it('renders loading, empty, and error states with retry recovery', async () => {
    fixture.detectChanges();
    const root = fixtureHost(fixture);
    expect(root.querySelectorAll('.upcoming-skeleton__row').length).toBeGreaterThan(0);

    facade.status.set('empty');
    fixture.detectChanges();
    expect(root.textContent).toContain('Nothing upcoming');

    facade.status.set('error');
    facade.error.set('Offline');
    fixture.detectChanges();
    expect(root.textContent).toContain('Offline');
    findButton('Try again').click();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(facade.refresh).toHaveBeenCalled();
    expect(facade.status()).toBe('ready');
  });

  it('renders grouped events with linked thumbs and status labels', () => {
    const now = new Date();
    const y = now.getFullYear();
    const m = String(now.getMonth() + 1).padStart(2, '0');
    const d0 = String(now.getDate()).padStart(2, '0');

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
        art: 'linear-gradient(145deg, #312e81, #0f172a 70%)',
        href: 'http://localhost:8989/series/cowboy-bebop',
      },
    ]);
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    expect(root.textContent).toContain('Today');
    expect(root.textContent).toContain('Cowboy Bebop');
    expect(root.textContent).toContain('Soon');
    expect(root.querySelector('.mm-status--warning')).not.toBeNull();
    const thumb = root.querySelector('a.up-next__thumb') as HTMLAnchorElement;
    expect(thumb.getAttribute('href')).toBe('http://localhost:8989/series/cowboy-bebop');
  });

  function findButton(label: string): HTMLButtonElement {
    const button = [...fixtureHost(fixture).querySelectorAll('button')].find((node) =>
      node.textContent.includes(label),
    );
    if (!button) throw new Error(`Missing button ${label}`);
    return button;
  }
});

function createFacade() {
  const status = signal<CalendarStatus>('loading');
  const events = signal<CalendarRailEvent[]>([]);
  const error = signal('');
  const refresh = vi.fn(() => {
    status.set('ready');
    return Promise.resolve();
  });
  return {
    status,
    events,
    error,
    refresh,
    groups: computed(() => groupCalendarEvents(events())),
  };
}

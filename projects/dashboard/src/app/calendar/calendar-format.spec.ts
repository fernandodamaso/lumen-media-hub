import { CALENDAR_KIND_VIEW, CALENDAR_STATUS_VIEW, groupCalendarEvents, mapCalendarEvent } from './calendar-format';

describe('calendar format / calendar mapping', () => {
  it('maps calendar DTO fields into rail domain values', () => {
    const event = mapCalendarEvent({
      title: 'Cowboy Bebop',
      additional: 'S1 E5',
      date: 'Jul 12',
      airDate: '2026-07-12T18:00:00Z',
      hasFile: true,
      kind: 'episode',
    });
    expect(event).toMatchObject({
      time: 'Jul 12',
      kind: 'episode',
      title: 'Cowboy Bebop',
      subtitle: 'S1 E5',
      status: 'available',
    });
  });

  it('maps kind and status labels with accessible tones', () => {
    expect(CALENDAR_KIND_VIEW.episode).toEqual({ label: 'Episode', tone: 'info' });
    expect(CALENDAR_KIND_VIEW.movie).toEqual({ label: 'Movie', tone: 'info' });
    expect(CALENDAR_STATUS_VIEW.available).toEqual({ label: 'Available', tone: 'success' });
    expect(CALENDAR_STATUS_VIEW.monitored).toEqual({ label: 'Monitored', tone: 'info' });
    expect(CALENDAR_STATUS_VIEW.premiere).toEqual({ label: 'Premiere', tone: 'premiere' });
    expect(CALENDAR_STATUS_VIEW.pending).toEqual({ label: 'Soon', tone: 'warning' });
  });

  it('derives status from file, monitored, and premiere indicators when missing', () => {
    const base = { title: 'Show', additional: 'S1 E1', date: '18:00' };
    expect(mapCalendarEvent({ ...base, hasFile: true }).status).toBe('available');
    expect(mapCalendarEvent({ ...base, monitored: true }).status).toBe('monitored');
    expect(mapCalendarEvent({ ...base, premiere: true }).status).toBe('premiere');
    expect(mapCalendarEvent({ ...base, additional: 'Movie · Premiere' }).status).toBe('premiere');
    expect(mapCalendarEvent(base).status).toBe('pending');
  });

  it('passes through known statuses and optional art', () => {
    const event = mapCalendarEvent({
      title: 'Dune',
      additional: 'Movie · Premiere',
      date: '00:00',
      status: 'premiere',
      hasFile: true,
      art: 'linear-gradient(145deg, #8b5a2b, #1a1410 70%)',
    });
    expect(event.status).toBe('premiere');
    expect(event.art).toBe('linear-gradient(145deg, #8b5a2b, #1a1410 70%)');
    expect(mapCalendarEvent({ title: 'Show', additional: 'S1 E1', date: '18:00' }).art).toContain('linear-gradient');
  });

  it('limits Upcoming groups to today, tomorrow, and the day after tomorrow', () => {
    const now = new Date(2026, 6, 22, 12); // Jul 22 2026 local
    const groups = groupCalendarEvents(
      [
        { airDate: '2026-07-22T12:30:00', title: 'Today' },
        { airDate: '2026-07-23T17:30:00', title: 'Tomorrow' },
        { airDate: '2026-07-24T14:30:00', title: 'Day after' },
        { airDate: '2026-07-25T14:00:00', title: 'Too far' },
        { airDate: '', title: 'Undated' },
      ],
      now,
    );
    expect(groups.map((group) => group.label)).toEqual(['TODAY', 'TOMORROW', 'FRIDAY']);
    expect(groups.flatMap((group) => group.events.map((event) => event.title))).toEqual([
      'Today',
      'Tomorrow',
      'Day after',
    ]);
  });
});

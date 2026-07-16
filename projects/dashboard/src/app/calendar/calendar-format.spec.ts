import { CALENDAR_KIND_VIEW, CALENDAR_STATUS_VIEW, mapCalendarEvent } from './calendar-format';

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
    expect(CALENDAR_STATUS_VIEW.pending).toEqual({ label: 'Upcoming', tone: 'warning' });
  });
});

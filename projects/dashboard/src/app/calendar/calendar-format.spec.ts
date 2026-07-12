import { CALENDAR_KIND_VIEW, CALENDAR_STATUS_VIEW } from './calendar-format';

describe('calendar-format', () => {
  it('maps kind and status labels with accessible tones', () => {
    expect(CALENDAR_KIND_VIEW.episode).toEqual({ label: 'Episode', tone: 'info' });
    expect(CALENDAR_KIND_VIEW.movie).toEqual({ label: 'Movie', tone: 'info' });
    expect(CALENDAR_STATUS_VIEW.available).toEqual({ label: 'Available', tone: 'success' });
    expect(CALENDAR_STATUS_VIEW.pending).toEqual({ label: 'Upcoming', tone: 'warning' });
  });
});

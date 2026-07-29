import { resolveWatchNextPageSize } from './watch-next-grid.page-size';

describe('resolveWatchNextPageSize', () => {
  it('matches compact poster column breakpoints', () => {
    expect(resolveWatchNextPageSize(1200)).toBe(5);
    expect(resolveWatchNextPageSize(900)).toBe(4);
    expect(resolveWatchNextPageSize(720)).toBe(3);
    expect(resolveWatchNextPageSize(520)).toBe(2);
    expect(resolveWatchNextPageSize(320)).toBe(2);
  });
});

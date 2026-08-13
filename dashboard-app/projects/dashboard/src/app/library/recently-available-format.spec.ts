import {
  formatAvailableAge,
  formatRecentlyAvailableCardSubtitle,
  isNewlyAvailable,
  mapRecentlyAvailableItem,
  mapRecentlyAvailableResult,
  recentlyAvailableLinkLabel,
} from './recently-available-format';
import { RecentlyAvailableItem } from './recently-available.models';
import { MediaStackRecentlyAvailableItemDto } from '../media-stack/wire/recently-available';

describe('recently-available-format', () => {
  const episodeDto: MediaStackRecentlyAvailableItemDto = {
    id: 'ep-1',
    parentId: 'series-1',
    kind: 'episode',
    title: 'Saga of Tanya the Evil',
    subtitle: 'S02E05 · Lamb',
    year: 2026,
    availableAt: '2026-08-11T12:14:33Z',
    posterUrl: 'https://example.com/tanya.jpg',
    artworkState: 'ok',
    thumbUrl: 'https://example.com/tanya-thumb.jpg',
    playable: true,
  };

  it('maps episode fields and preserves thumbUrl', () => {
    const item = mapRecentlyAvailableItem(episodeDto);
    expect(item.href).toBeNull();
    expect(item.playable).toBe(true);
    expect(item.thumbUrl).toBe('https://example.com/tanya-thumb.jpg');
    expect(item.art).toContain('https://example.com/tanya.jpg');
  });

  it('maps movie with null parent and empty subtitle', () => {
    const item = mapRecentlyAvailableItem({
      ...episodeDto,
      id: 'mv-1',
      parentId: null,
      kind: 'movie',
      title: 'Mickey 17',
      subtitle: '',
      thumbUrl: null,
    });
    expect(item.parentId).toBeNull();
    expect(item.subtitle).toBe('');
  });

  it('sorts mapped results newest-first', () => {
    const result = mapRecentlyAvailableResult([
      {
        ...episodeDto,
        id: 'older',
        availableAt: '2026-08-09T08:00:00Z',
      },
      {
        ...episodeDto,
        id: 'newer',
        availableAt: '2026-08-11T12:14:33Z',
      },
    ]);
    expect(result.items.map((item) => item.id)).toEqual(['newer', 'older']);
  });

  it('uses missing artwork fallback', () => {
    const item = mapRecentlyAvailableItem({
      ...episodeDto,
      posterUrl: undefined,
      artworkState: 'missing',
    });
    expect(item.artworkState).toBe('missing');
    expect(item.art).toContain('gradient');
  });

  describe('formatAvailableAge', () => {
    const now = new Date('2026-08-11T14:00:00Z');

    it('handles invalid and far-future timestamps', () => {
      expect(formatAvailableAge('invalid', now)).toBe('Ready time unavailable');
      expect(formatAvailableAge('2026-08-11T14:06:01Z', now)).toBe('Ready time unavailable');
      expect(isNewlyAvailable('2026-08-11T14:06:01Z', now)).toBe(false);
    });

    it('formats near-now and minute/hour/day buckets', () => {
      expect(formatAvailableAge('2026-08-11T14:00:00Z', now)).toBe('Ready now');
      expect(formatAvailableAge('2026-08-11T13:59:01Z', now)).toBe('Ready now');
      expect(formatAvailableAge('2026-08-11T13:55:00Z', now)).toBe('Ready 5m ago');
      expect(formatAvailableAge('2026-08-11T13:00:01Z', now)).toBe('Ready 59m ago');
      expect(formatAvailableAge('2026-08-11T13:00:00Z', now)).toBe('Ready 1h ago');
      expect(formatAvailableAge('2026-08-11T12:00:00Z', now)).toBe('Ready 2h ago');
      expect(formatAvailableAge('2026-08-11T14:00:01Z', now)).toBe('Ready now');
      expect(formatAvailableAge('2026-08-10T14:00:01Z', now)).toBe('Ready 23h ago');
      expect(formatAvailableAge('2026-08-10T14:00:00Z', now)).toBe('Ready yesterday');
      expect(formatAvailableAge('2026-08-09T14:00:01Z', now)).toBe('Ready yesterday');
      expect(formatAvailableAge('2026-08-09T14:00:00Z', now)).toBe('Ready 2d ago');
      expect(formatAvailableAge('2026-08-08T14:00:00Z', now)).toBe('Ready 3d ago');
      expect(formatAvailableAge('2026-08-04T14:00:01Z', now)).toBe('Ready 6d ago');
      expect(formatAvailableAge('2026-08-04T14:00:00Z', now)).toBe('Ready Aug 4');
      expect(formatAvailableAge('2026-08-01T14:00:00Z', now)).toBe('Ready Aug 1');
    });

    it('uses UTC absolute dates independent of local timezone', () => {
      const utcNow = new Date('2026-08-11T00:00:00Z');
      expect(formatAvailableAge('2026-08-04T00:00:00Z', utcNow)).toBe('Ready Aug 4');
    });
  });

  describe('isNewlyAvailable', () => {
    const now = new Date('2026-08-11T14:00:00Z');

    it('is true only inside the 24h window with future skew', () => {
      expect(isNewlyAvailable('2026-08-11T14:05:00Z', now)).toBe(true);
      expect(isNewlyAvailable('2026-08-10T14:00:01Z', now)).toBe(true);
      expect(isNewlyAvailable('2026-08-10T14:00:00Z', now)).toBe(false);
      expect(isNewlyAvailable('2026-08-11T14:06:01Z', now)).toBe(false);
    });
  });

  describe('card presentation helpers', () => {
    const now = new Date('2026-08-11T14:00:00Z');

    const episode = (overrides: Partial<RecentlyAvailableItem> = {}): RecentlyAvailableItem => ({
      id: 'ep-1',
      parentId: 'series-1',
      title: 'Saga of Tanya the Evil',
      subtitle: 'S02E05 · Lamb',
      kind: 'episode',
      availableAt: '2026-08-11T12:00:00Z',
      art: 'linear-gradient(#111, #222)',
      artworkState: 'ok',
      thumbUrl: null,
      href: null,
      playable: true,
      year: 2026,
      ...overrides,
    });

    it('formats episode and movie card subtitles', () => {
      expect(formatRecentlyAvailableCardSubtitle(episode(), now)).toBe(
        'S02E05 · Lamb · Ready 2h ago',
      );
      expect(
        formatRecentlyAvailableCardSubtitle(
          episode({ kind: 'movie', parentId: null, subtitle: '', year: 2025 }),
          now,
        ),
      ).toBe('2025 · Movie · Ready 2h ago');
      expect(
        formatRecentlyAvailableCardSubtitle(
          episode({ kind: 'movie', parentId: null, subtitle: '', year: null }),
          now,
        ),
      ).toBe('Movie · Ready 2h ago');
    });

    it('builds distinct accessible link labels for episodes and movies', () => {
      expect(recentlyAvailableLinkLabel(episode())).toBe(
        'Open Saga of Tanya the Evil, S02E05, Lamb in Jellyfin',
      );
      expect(
        recentlyAvailableLinkLabel(
          episode({ subtitle: 'S02E06 · Other', title: 'Saga of Tanya the Evil' }),
        ),
      ).toBe('Open Saga of Tanya the Evil, S02E06, Other in Jellyfin');
      expect(
        recentlyAvailableLinkLabel(
          episode({ kind: 'movie', parentId: null, subtitle: '', title: 'Mickey 17', year: 2025 }),
        ),
      ).toBe('Open Mickey 17, 2025 in Jellyfin');
      expect(
        recentlyAvailableLinkLabel(
          episode({ kind: 'movie', parentId: null, subtitle: '', title: 'Mickey 17', year: null }),
        ),
      ).toBe('Open Mickey 17 in Jellyfin');
    });
  });
});

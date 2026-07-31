import { mapActivityFeed, mapActivityItem } from './activity-format';
import { ActivityKind, ActivitySource, ActivitySourceStatus } from './activity.models';
import {
  MediaStackActivityKindDto,
  MediaStackActivitySourceDto,
  MediaStackActivitySourceStatusDto,
} from '../media-stack/wire/activity';

describe('activity-format', () => {
  it('maps activity items and feeds', () => {
    const source: ActivitySource = 'sonarr';
    const kind: ActivityKind = 'grabbed';
    const status: ActivitySourceStatus = 'ok';
    const dtoSource: MediaStackActivitySourceDto = source;
    const dtoKind: MediaStackActivityKindDto = kind;
    const dtoStatus: MediaStackActivitySourceStatusDto = status;

    const item = mapActivityItem({
      id: 'sonarr:1',
      source: dtoSource,
      kind: dtoKind,
      title: 'Show',
      subtitle: 'S01E01',
      timestamp: '2026-07-30T00:00:00Z',
      href: null,
    });
    expect(item.title).toBe('Show');

    const feed = mapActivityFeed({
      ok: true,
      generatedAt: '2026-07-30T00:00:00Z',
      sources: { sonarr: dtoStatus, radarr: 'ok' },
      items: [
        {
          id: 'sonarr:1',
          source: dtoSource,
          kind: dtoKind,
          title: 'Show',
          subtitle: 'S01E01',
          timestamp: '2026-07-30T00:00:00Z',
          href: null,
        },
      ],
    });
    expect(feed.items).toHaveLength(1);
  });
});

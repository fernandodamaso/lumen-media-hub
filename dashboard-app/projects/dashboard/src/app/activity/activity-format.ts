import { ActivityFeed, ActivityItem } from './activity.models';
import { MediaStackActivityFeedDto, MediaStackActivityItemDto } from '../media-stack/wire/activity';

export const mapActivityItem = (dto: MediaStackActivityItemDto): ActivityItem => ({
  id: dto.id,
  source: dto.source,
  kind: dto.kind,
  title: dto.title,
  subtitle: dto.subtitle,
  timestamp: dto.timestamp,
  href: dto.href,
});

export const mapActivityFeed = (dto: MediaStackActivityFeedDto): ActivityFeed => ({
  ok: dto.ok,
  generatedAt: dto.generatedAt,
  sources: { ...dto.sources },
  items: dto.items.map(mapActivityItem),
});

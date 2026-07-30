/** Raw activity feed payload stays behind this boundary. */
export type MediaStackActivitySourceDto = 'sonarr' | 'radarr';
export type MediaStackActivityKindDto = 'grabbed' | 'imported' | 'deleted' | 'failed';
export type MediaStackActivitySourceStatusDto = 'ok' | 'error' | 'unconfigured';

export interface MediaStackActivityItemDto {
  id: string;
  source: MediaStackActivitySourceDto;
  kind: MediaStackActivityKindDto;
  title: string;
  subtitle: string;
  timestamp: string;
  href: string | null;
}

export interface MediaStackActivityFeedDto {
  ok: boolean;
  generatedAt: string;
  sources: Record<MediaStackActivitySourceDto, MediaStackActivitySourceStatusDto>;
  items: MediaStackActivityItemDto[];
}

export type ActivitySource = 'sonarr' | 'radarr';
export type ActivityKind = 'grabbed' | 'imported' | 'deleted' | 'failed';
export type ActivitySourceStatus = 'ok' | 'error' | 'unconfigured';

export interface ActivityItem {
  id: string;
  source: ActivitySource;
  kind: ActivityKind;
  title: string;
  /** e.g. "S01E07 · 1080p WEB-DL" or "2021 · 2160p WEB-DL". */
  subtitle: string;
  timestamp: string;
  href: string | null;
}

export interface ActivityFeed {
  ok: boolean;
  generatedAt: string;
  sources: Record<ActivitySource, ActivitySourceStatus>;
  items: ActivityItem[];
}

/** Raw Sonarr/Radarr calendar payload stays behind this boundary. */
export interface MediaStackCalendarEventDto {
  id?: string;
  title: string;
  additional: string;
  date: string;
  airDate?: string;
  hasFile?: boolean;
  kind?: 'episode' | 'movie';
  episodeId?: number;
  movieId?: number;
  titleSlug?: string;
  seriesId?: number;
  monitored?: boolean;
  premiere?: boolean;
  status?: string;
  art?: string;
}

export interface MediaStackArrLibraryDto {
  ok: boolean;
  series: Record<string, string>;
  movies: Record<string, string>;
  error?: string;
}
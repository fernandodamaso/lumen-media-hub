/** Raw cron-log run from GET /cron/logs. Status values stay contract-shaped. */
export interface MediaStackCronLogRunDto {
  timestamp?: string;
  exitCode?: number;
  status?: string;
  applied?: number;
  evaluated?: number;
  skipped?: number;
  fatal?: string | null;
  detail?: string;
  highlights?: string[];
}

/** Per-job cron log entry from GET /cron/logs. */
export interface MediaStackCronLogEntryDto {
  id: string;
  title: string;
  file: string;
  format: string;
  schedule: string;
  description?: string;
  actions?: string[];
  exists: boolean;
  size?: number;
  mtime?: string | null;
  /** Most recent run (append-order); always present, even as a `missing` sentinel. */
  current: MediaStackCronLogRunDto;
  /** Older runs, oldest first; always present, possibly empty. */
  history: MediaStackCronLogRunDto[];
}

/** Envelope returned by GET /cron/logs. */
export interface MediaStackCronLogsDto {
  ok: boolean;
  generatedAt?: string;
  tmpDir?: string;
  logs?: MediaStackCronLogEntryDto[];
  note?: string;
  error?: string;
}

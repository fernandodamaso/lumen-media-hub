import { InjectionToken } from '@angular/core';

import { ArrLibrary, CalendarEvent } from '../calendar/calendar.models';
import {
  DiscoverAction,
  DiscoverFeedback,
  DiscoverRequestPayload,
  ExternalDiscover,
  HermesDiscover,
  JellyseerrDiscoverKind,
  TraktDiscoverType,
} from '../discover/discover.models';
import { DownloadTorrent } from '../downloads/downloads.models';
import {
  LibraryItemKind,
  LibraryListResult,
  LibraryStats,
} from '../library/library.models';
import { WatchNextResult } from '../library/watch-next.models';
import { AutomationSummary } from '../automation/automation.models';
import { CronLogs } from '../reports/reports.models';
import { StorageOverview } from '../storage/storage.models';

export interface MediaStackApi {
  listTorrents(signal?: AbortSignal): Promise<DownloadTorrent[]>;
  pauseAll(): Promise<void>;
  resumeAll(): Promise<void>;
  pauseTorrent(id: string): Promise<void>;
  resumeTorrent(id: string): Promise<void>;
  listCalendarEvents(signal?: AbortSignal): Promise<CalendarEvent[]>;
  getArrLibrary(signal?: AbortSignal): Promise<ArrLibrary>;
  listLibraryItems(filter?: { kind?: LibraryItemKind }, signal?: AbortSignal): Promise<LibraryListResult>;
  listWatchNext(signal?: AbortSignal): Promise<WatchNextResult>;
  getLibraryStats(signal?: AbortSignal): Promise<LibraryStats>;
  getStorageOverview(signal?: AbortSignal): Promise<StorageOverview>;
  getAutomationSummary(signal?: AbortSignal): Promise<AutomationSummary>;
  listCronLogs(signal?: AbortSignal): Promise<CronLogs>;
  listHermesRecommendations(signal?: AbortSignal): Promise<HermesDiscover>;
  submitHermesFeedback(id: string, feedback: DiscoverFeedback, notes?: string): Promise<DiscoverAction>;
  requestHermesMore(): Promise<DiscoverAction>;
  listJellyseerrDiscover(kind: JellyseerrDiscoverKind, signal?: AbortSignal): Promise<ExternalDiscover>;
  listTraktDiscover(type: TraktDiscoverType, signal?: AbortSignal): Promise<ExternalDiscover>;
  requestMedia(payload: DiscoverRequestPayload): Promise<DiscoverAction>;
}

export const MEDIA_STACK_API = new InjectionToken<MediaStackApi>('MEDIA_STACK_API');

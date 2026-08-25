import { InjectionToken } from '@angular/core';

import { ArrLibrary, CalendarEventCollection } from '../calendar/calendar.models';
import {
  DiscoverAction,
  DiscoverFeedback,
  DiscoverRequestPayload,
  ExternalDiscover,
  HermesDiscover,
  JellyseerrDiscoverKind,
  SubmitHermesFeedbackOptions,
  TraktDiscoverType,
} from '../discover/discover.models';
import { DownloadTorrent } from '../downloads/downloads.models';
import {
  LibraryItemKind,
  LibraryListResult,
  LibraryStats,
  LibraryDeletePreview,
  LibraryDeleteResult,
  DirectDeleteResult,
} from '../library/library.models';
import { WatchNextResult } from '../library/watch-next.models';
import { RecentlyAvailableResult } from '../library/recently-available.models';
import { ActivityFeed } from '../activity/activity.models';
import { AutomationSummary, QueueHygieneRunResult } from '../automation/automation.models';
import { CronLogs } from '../reports/reports.models';
import { StorageOverview } from '../storage/storage.models';

export interface MediaStackApi {
  listTorrents(signal?: AbortSignal): Promise<DownloadTorrent[]>;
  pauseAll(): Promise<void>;
  resumeAll(): Promise<void>;
  pauseTorrent(id: string): Promise<void>;
  resumeTorrent(id: string): Promise<void>;
  listCalendarEvents(signal?: AbortSignal): Promise<CalendarEventCollection>;
  getArrLibrary(signal?: AbortSignal): Promise<ArrLibrary>;
  listLibraryItems(filter?: { kind?: LibraryItemKind }, signal?: AbortSignal): Promise<LibraryListResult>;
  setLibraryItemPlayed(id: string, played: boolean): Promise<{ played: boolean }>;
  previewLibraryItemDeletion(id: string): Promise<LibraryDeletePreview>;
  deleteLibraryItem(id: string, previewId: string): Promise<LibraryDeleteResult>;
  deleteLibraryItemDirectly(id: string): Promise<DirectDeleteResult>;
  listWatchNext(signal?: AbortSignal): Promise<WatchNextResult>;
  listRecentlyAvailable(limit?: number, signal?: AbortSignal): Promise<RecentlyAvailableResult>;
  getActivity(limit?: number, signal?: AbortSignal): Promise<ActivityFeed>;
  getLibraryStats(signal?: AbortSignal): Promise<LibraryStats>;
  getStorageOverview(signal?: AbortSignal): Promise<StorageOverview>;
  getAutomationSummary(signal?: AbortSignal): Promise<AutomationSummary>;
  runQueueHygiene(mode: 'observe' | 'auto'): Promise<QueueHygieneRunResult>;
  listCronLogs(signal?: AbortSignal): Promise<CronLogs>;
  listHermesRecommendations(signal?: AbortSignal): Promise<HermesDiscover>;
  submitHermesFeedback(
    id: string,
    feedback: DiscoverFeedback,
    options?: SubmitHermesFeedbackOptions,
  ): Promise<DiscoverAction>;
  requestHermesMore(): Promise<DiscoverAction>;
  listJellyseerrDiscover(kind: JellyseerrDiscoverKind, signal?: AbortSignal): Promise<ExternalDiscover>;
  listTraktDiscover(type: TraktDiscoverType, signal?: AbortSignal): Promise<ExternalDiscover>;
  requestMedia(payload: DiscoverRequestPayload): Promise<DiscoverAction>;
}

export const MEDIA_STACK_API = new InjectionToken<MediaStackApi>('MEDIA_STACK_API');

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
import { LibraryItem, LibraryItemKind, LibraryStats } from '../library/library.models';
import { AutomationSummary } from '../automation/automation.models';
import { CronLogs } from '../reports/reports.models';
import { StorageOverview } from '../storage/storage.models';

export interface MediaStackApi {
  listTorrents(): Promise<DownloadTorrent[]>;
  pauseAll(): Promise<void>;
  resumeAll(): Promise<void>;
  pauseTorrent(id: string): Promise<void>;
  resumeTorrent(id: string): Promise<void>;
  listCalendarEvents(): Promise<CalendarEvent[]>;
  getArrLibrary(): Promise<ArrLibrary>;
  listLibraryItems(filter?: { kind?: LibraryItemKind }): Promise<LibraryItem[]>;
  getLibraryStats(): Promise<LibraryStats>;
  getStorageOverview(): Promise<StorageOverview>;
  getAutomationSummary(): Promise<AutomationSummary>;
  listCronLogs(): Promise<CronLogs>;
  listHermesRecommendations(): Promise<HermesDiscover>;
  submitHermesFeedback(id: string, feedback: DiscoverFeedback, notes?: string): Promise<DiscoverAction>;
  requestHermesMore(): Promise<DiscoverAction>;
  listJellyseerrDiscover(kind: JellyseerrDiscoverKind): Promise<ExternalDiscover>;
  listTraktDiscover(type: TraktDiscoverType): Promise<ExternalDiscover>;
  requestMedia(payload: DiscoverRequestPayload): Promise<DiscoverAction>;
}

export const MEDIA_STACK_API = new InjectionToken<MediaStackApi>('MEDIA_STACK_API');

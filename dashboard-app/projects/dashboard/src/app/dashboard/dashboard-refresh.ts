import { AutomationFacade } from '../automation/automation.facade';
import { ServiceHealthFacade } from '../automation/service-health.facade';
import { CalendarFacade } from '../calendar/calendar.facade';
import { DownloadsFacade } from '../downloads/downloads.facade';
import { LibraryItemsFacade } from '../library/library-items.facade';
import { LibraryStatsFacade } from '../library/library-stats.facade';
import { RecentlyAvailableFacade } from '../library/recently-available.facade';
import { WatchNextFacade } from '../library/watch-next.facade';
import { ActivityFacade } from '../right-rail/activity.facade';
import { StorageFacade } from '../storage/storage.facade';
import { TrendingFacade } from './trending.facade';

/** Facades refreshed by a single manual dashboard refresh (no poll loops started). */
export type DashboardRefreshDeps = {
  health: ServiceHealthFacade;
  libraryItems: LibraryItemsFacade;
  libraryStats: LibraryStatsFacade;
  watchNext: WatchNextFacade;
  recentlyAvailable: RecentlyAvailableFacade;
  downloads: DownloadsFacade;
  storage: StorageFacade;
  calendar: CalendarFacade;
  automation: AutomationFacade;
  activity: ActivityFacade;
  trending: TrendingFacade;
};

/** Refresh every dashboard data source exactly once (matches dashboard page manual refresh). */
export async function refreshDashboardData(deps: DashboardRefreshDeps): Promise<void> {
  await Promise.all([
    deps.health.refresh(),
    deps.libraryItems.refresh(),
    deps.libraryStats.refresh(),
    deps.watchNext.refresh(),
    deps.recentlyAvailable.refresh(),
    deps.downloads.refresh(),
    deps.storage.refresh(),
    deps.calendar.refresh(),
    deps.automation.refresh(),
    deps.activity.refresh(),
    deps.trending.refresh(),
  ]);
}

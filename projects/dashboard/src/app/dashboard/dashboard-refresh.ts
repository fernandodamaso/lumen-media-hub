import { AutomationFacade } from '../automation/automation.facade';
import { ServiceHealthFacade } from '../automation/service-health.facade';
import { CalendarFacade } from '../calendar/calendar.facade';
import { DownloadsFacade } from '../downloads/downloads.facade';
import { LibraryItemsFacade } from '../library/library-items.facade';
import { LibraryStatsFacade } from '../library/library-stats.facade';
import { WatchNextFacade } from '../library/watch-next.facade';
import { StorageFacade } from '../storage/storage.facade';

/** Refresh every dashboard data source (matches dashboard page manual refresh). */
export async function refreshDashboardData(deps: {
  health: ServiceHealthFacade;
  libraryItems: LibraryItemsFacade;
  libraryStats: LibraryStatsFacade;
  watchNext: WatchNextFacade;
  downloads: DownloadsFacade;
  storage: StorageFacade;
  calendar: CalendarFacade;
  automation: AutomationFacade;
}): Promise<void> {
  await Promise.all([
    deps.health.refresh(),
    deps.libraryItems.refresh(),
    deps.libraryStats.refresh(),
    deps.watchNext.refresh(),
    deps.downloads.refresh(),
    deps.storage.refresh(),
    deps.calendar.refresh(),
    deps.automation.refresh(),
  ]);
}

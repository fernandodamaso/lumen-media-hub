import { vi } from 'vitest';
import { DashboardRefreshDeps, refreshDashboardData } from './dashboard-refresh';

describe('refreshDashboardData', () => {
  it('refreshes watch-next, recently-available, and activity together with other dashboard sources', async () => {
    const refresh = vi.fn().mockResolvedValue(undefined);
    const watchNextRefresh = vi.fn().mockResolvedValue(undefined);
    const recentlyAvailableRefresh = vi.fn().mockResolvedValue(undefined);
    const activityRefresh = vi.fn().mockResolvedValue(undefined);
    const trendingRefresh = vi.fn().mockResolvedValue(undefined);
    const deps = {
      health: { refresh },
      libraryItems: { refresh },
      libraryStats: { refresh },
      watchNext: { refresh: watchNextRefresh },
      recentlyAvailable: { refresh: recentlyAvailableRefresh },
      downloads: { refresh },
      storage: { refresh },
      calendar: { refresh },
      automation: { refresh },
      activity: { refresh: activityRefresh },
      trending: { refresh: trendingRefresh },
    } as unknown as DashboardRefreshDeps;

    await refreshDashboardData(deps);

    expect(refresh).toHaveBeenCalledTimes(7);
    expect(watchNextRefresh).toHaveBeenCalledTimes(1);
    expect(recentlyAvailableRefresh).toHaveBeenCalledTimes(1);
    expect(activityRefresh).toHaveBeenCalledTimes(1);
    expect(trendingRefresh).toHaveBeenCalledTimes(1);
  });
});

import { vi } from 'vitest';
import { DashboardRefreshDeps, refreshDashboardData } from './dashboard-refresh';

describe('refreshDashboardData', () => {
  it('refreshes watch-next and activity together with other dashboard sources', async () => {
    const refresh = vi.fn().mockResolvedValue(undefined);
    const watchNextRefresh = vi.fn().mockResolvedValue(undefined);
    const activityRefresh = vi.fn().mockResolvedValue(undefined);
    const deps = {
      health: { refresh },
      libraryItems: { refresh },
      libraryStats: { refresh },
      watchNext: { refresh: watchNextRefresh },
      downloads: { refresh },
      storage: { refresh },
      calendar: { refresh },
      automation: { refresh },
      activity: { refresh: activityRefresh },
    } as unknown as DashboardRefreshDeps;

    await refreshDashboardData(deps);

    expect(refresh).toHaveBeenCalledTimes(7);
    expect(watchNextRefresh).toHaveBeenCalledTimes(1);
    expect(activityRefresh).toHaveBeenCalledTimes(1);
  });
});

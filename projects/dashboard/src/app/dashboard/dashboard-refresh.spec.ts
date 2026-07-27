import { vi } from 'vitest';
import { refreshDashboardData } from './dashboard-refresh';

describe('refreshDashboardData', () => {
  it('refreshes watch-next together with other dashboard sources', async () => {
    const refresh = vi.fn().mockResolvedValue(undefined);
    const watchNextRefresh = vi.fn().mockResolvedValue(undefined);
    const deps = {
      health: { refresh },
      libraryItems: { refresh },
      libraryStats: { refresh },
      watchNext: { refresh: watchNextRefresh },
      downloads: { refresh },
      storage: { refresh },
      calendar: { refresh },
      automation: { refresh },
    };

    await refreshDashboardData(
      deps as unknown as Parameters<typeof refreshDashboardData>[0],
    );

    expect(refresh).toHaveBeenCalledTimes(7);
    expect(watchNextRefresh).toHaveBeenCalledTimes(1);
  });
});

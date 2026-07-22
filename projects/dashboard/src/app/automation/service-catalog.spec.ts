import { describe, expect, it } from 'vitest';
import {
  resolveServiceHref,
  SERVICE_CATALOG,
  visibleServiceCatalog,
} from './service-catalog';

describe('service catalog', () => {
  it('includes SABnzbd only for Demo mode', () => {
    expect(visibleServiceCatalog(false).some((entry) => entry.id === 'sabnzbd')).toBe(true);
    expect(visibleServiceCatalog(true).some((entry) => entry.id === 'sabnzbd')).toBe(false);
    expect(SERVICE_CATALOG.find((entry) => entry.id === 'sabnzbd')?.demoOnly).toBe(true);
  });

  it('resolves trailing-slash bases into external hrefs', () => {
    expect(resolveServiceHref('jellyfin', { jellyfin: 'http://localhost:8096/' })).toBe(
      'http://localhost:8096/',
    );
    expect(resolveServiceHref('sonarr', { sonarr: 'http://localhost:8989' })).toBe(
      'http://localhost:8989/',
    );
    expect(resolveServiceHref('sabnzbd', {})).toBeNull();
    expect(resolveServiceHref('jellyfin', {})).toBeNull();
  });
});

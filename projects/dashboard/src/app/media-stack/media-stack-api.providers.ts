import { InjectionToken, Provider } from '@angular/core';

import { environment } from '../../environments/environment';
import { CALENDAR_LINK_BASES } from '../calendar/calendar.models';
import { JELLYFIN_LINK_BASES } from '../library/library.models';
import { MEDIA_STACK_API } from './media-stack-api';
import { HttpMediaStackApi } from './http-media-stack-api';
import { MockMediaStackApi } from './mock-media-stack-api';

export { JELLYFIN_LINK_BASES } from '../library/library.models';
export type { JellyfinLinkBases } from '../library/library.models';

/** Bind MediaStackApi to mock (default) or HTTP adapter when live env is selected. */
export function provideMediaStackApi(): Provider[] {
  return [
    {
      provide: MEDIA_STACK_API,
      useClass: environment.useLiveApi ? HttpMediaStackApi : MockMediaStackApi,
    },
  ];
}

export interface ServiceLinkBases {
  jellyfin?: string;
  sonarr?: string;
  radarr?: string;
  prowlarr?: string;
  qbittorrent?: string;
  bazarr?: string;
}

/** Disabled by default; local Demo/live inject bases from environment. */
export const SERVICE_LINK_BASES = new InjectionToken<ServiceLinkBases>('SERVICE_LINK_BASES', {
  providedIn: 'root',
  factory: () => ({}),
});

/** Jellyfin / Sonarr / Radarr deep-link bases from the active environment. */
export function provideOperationalLinkBases(): Provider[] {
  return [
    {
      provide: JELLYFIN_LINK_BASES,
      useValue: { jellyfinBase: environment.jellyfinBase },
    },
    {
      provide: CALENDAR_LINK_BASES,
      useValue: {
        sonarrBase: environment.sonarrBase,
        radarrBase: environment.radarrBase,
      },
    },
    {
      provide: SERVICE_LINK_BASES,
      useValue: {
        jellyfin: environment.jellyfinBase,
        sonarr: environment.sonarrBase,
        radarr: environment.radarrBase,
        prowlarr: environment.prowlarrBase,
        qbittorrent: environment.qbittorrentBase,
        bazarr: environment.bazarrBase,
      } satisfies ServiceLinkBases,
    },
  ];
}

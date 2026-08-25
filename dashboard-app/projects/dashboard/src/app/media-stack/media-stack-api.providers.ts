import { HttpClient } from '@angular/common/http';
import {
  EnvironmentProviders,
  inject,
  InjectionToken,
  provideAppInitializer,
  Provider,
} from '@angular/core';
import { firstValueFrom } from 'rxjs';

import { environment } from '../../environments/environment';
import { CALENDAR_LINK_BASES, CalendarLinkBases } from '../calendar/calendar.models';
import { JELLYFIN_LINK_BASES, JellyfinLinkBases } from '../library/library.models';
import { MEDIA_STACK_API } from './media-stack-api';
import { LiveCalendarHttpMediaStackApi } from './live-calendar-http-media-stack-api';
import { MockMediaStackApi, DownloadsScenario } from './mock-media-stack-api';


/** Bind MediaStackApi to mock (default) or HTTP adapter when live env is selected. */
export function provideMediaStackApi(): Provider[] {
  if (environment.useLiveApi) {
    return [
      { provide: MEDIA_STACK_API, useClass: LiveCalendarHttpMediaStackApi },
    ];
  }
  return [
    {
      provide: MEDIA_STACK_API,
      useFactory: () => {
        const mock = new MockMediaStackApi();
        const params = new URLSearchParams(globalThis.location.search);
        const scenario = params.get('scenario');
        if (scenario?.startsWith('downloads-')) {
          const name = scenario.slice('downloads-'.length) as DownloadsScenario;
          switch (name) {
            case 'default': case 'empty': case 'error': case 'paused': case 'mixed':
              mock.setDownloadsScenario(name);
          }
        }
        const latency = params.get('latency');
        if (latency !== null) {
          const n = Number(latency);
          if (Number.isFinite(n) && n >= 0) {
            mock.latencyMs = n;
          }
        }
        return mock;
      },
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

function environmentServiceLinks(): Required<ServiceLinkBases> {
  return {
    jellyfin: environment.jellyfinBase,
    sonarr: environment.sonarrBase,
    radarr: environment.radarrBase,
    prowlarr: environment.prowlarrBase,
    qbittorrent: environment.qbittorrentBase,
    bazarr: environment.bazarrBase,
  };
}

/** Apply host-published bases from homepage-actions onto the injectable holders. */
export function applyServiceLinkBases(
  links: ServiceLinkBases,
  serviceLinkBases: ServiceLinkBases,
  jellyfinLinkBases: JellyfinLinkBases,
  calendarLinkBases: CalendarLinkBases,
): void {
  const jellyfin = normalizeBase(links.jellyfin);
  const sonarr = normalizeBase(links.sonarr);
  const radarr = normalizeBase(links.radarr);
  const prowlarr = normalizeBase(links.prowlarr);
  const qbittorrent = normalizeBase(links.qbittorrent);
  const bazarr = normalizeBase(links.bazarr);

  if (jellyfin) {
    serviceLinkBases.jellyfin = jellyfin;
    jellyfinLinkBases.jellyfinBase = jellyfin;
  }
  if (sonarr) {
    serviceLinkBases.sonarr = sonarr;
    calendarLinkBases.sonarrBase = sonarr;
  }
  if (radarr) {
    serviceLinkBases.radarr = radarr;
    calendarLinkBases.radarrBase = radarr;
  }
  if (prowlarr) serviceLinkBases.prowlarr = prowlarr;
  if (qbittorrent) serviceLinkBases.qbittorrent = qbittorrent;
  if (bazarr) serviceLinkBases.bazarr = bazarr;
}

function normalizeBase(value: string | undefined): string | undefined {
  const trimmed = value?.trim().replace(/\/$/, '');
  return trimmed || undefined;
}

/** Jellyfin / Sonarr / Radarr deep-link bases from the active environment (Live: overwritten by /service-links). */
export function provideOperationalLinkBases(): Array<Provider | EnvironmentProviders> {
  const serviceLinkBases: ServiceLinkBases = environmentServiceLinks();
  const jellyfinLinkBases: JellyfinLinkBases = { jellyfinBase: environment.jellyfinBase };
  const calendarLinkBases: CalendarLinkBases = {
    sonarrBase: environment.sonarrBase,
    radarrBase: environment.radarrBase,
  };

  const providers: Array<Provider | EnvironmentProviders> = [
    {
      provide: JELLYFIN_LINK_BASES,
      useValue: jellyfinLinkBases,
    },
    {
      provide: CALENDAR_LINK_BASES,
      useValue: calendarLinkBases,
    },
    {
      provide: SERVICE_LINK_BASES,
      useValue: serviceLinkBases,
    },
  ];

  if (environment.useLiveApi) {
    providers.push(
      provideAppInitializer(() => {
        const http = inject(HttpClient);
        const apiBase = environment.apiBaseUrl.replace(/\/$/, '');
        return firstValueFrom(http.get<ServiceLinkBases>(`${apiBase}/service-links`))
          .then((links) => {
            applyServiceLinkBases(links, serviceLinkBases, jellyfinLinkBases, calendarLinkBases);
          })
          .catch(() => undefined);
      }),
    );
  }

  return providers;
}

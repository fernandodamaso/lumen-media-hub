import { ApplicationInitStatus } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';

import { environment } from '../../environments/environment';
import { CALENDAR_LINK_BASES } from '../calendar/calendar.models';
import { JELLYFIN_LINK_BASES } from '../library/library.models';
import { MEDIA_STACK_API } from './media-stack-api';
import { HttpMediaStackApi } from './http-media-stack-api';
import { MockMediaStackApi } from './mock-media-stack-api';
import {
  SERVICE_LINK_BASES,
  applyServiceLinkBases,
  provideMediaStackApi,
  provideOperationalLinkBases,
} from './media-stack-api.providers';

async function withMockLocation(search: string, fn: () => void | Promise<void>): Promise<void> {
  const original = globalThis.location;
  const mock = { search } as Location;
  Object.defineProperty(globalThis, 'location', { value: mock, configurable: true, writable: true });
  try {
    await fn();
  } finally {
    Object.defineProperty(globalThis, 'location', { value: original, configurable: true, writable: true });
  }
}

describe('provideMediaStackApi', () => {
  afterEach(() => {
    TestBed.resetTestingModule();
  });

  it('binds Demo mode to MockMediaStackApi', () => {
    expect(environment.useLiveApi).toBe(false);

    TestBed.configureTestingModule({
      providers: [...provideMediaStackApi()],
    });

    expect(TestBed.inject(MEDIA_STACK_API)).toBeInstanceOf(MockMediaStackApi);
  });

  it('binds Live mode to HttpMediaStackApi', () => {
    const previous = environment.useLiveApi;
    (environment as { useLiveApi: boolean }).useLiveApi = true;

    try {
      TestBed.configureTestingModule({
        providers: [provideHttpClient(), ...provideMediaStackApi()],
      });
      expect(TestBed.inject(MEDIA_STACK_API)).toBeInstanceOf(HttpMediaStackApi);
    } finally {
      (environment as { useLiveApi: boolean }).useLiveApi = previous;
    }
  });

  describe('latency URL param (demo mode)', () => {
    it('defaults to 0 when param is missing', () => {
      TestBed.configureTestingModule({
        providers: [...provideMediaStackApi()],
      });
      const api = TestBed.inject(MEDIA_STACK_API) as MockMediaStackApi;
      expect(api.latencyMs).toBe(0);
    });

    it('applies latency from URL param', async () => {
      await withMockLocation('?latency=500', () => {
        TestBed.configureTestingModule({
          providers: [...provideMediaStackApi()],
        });
        const api = TestBed.inject(MEDIA_STACK_API) as MockMediaStackApi;
        expect(api.latencyMs).toBe(500);
      });
    });

    it('ignores invalid latency values silently', async () => {
      await withMockLocation('?latency=abc', () => {
        TestBed.configureTestingModule({
          providers: [...provideMediaStackApi()],
        });
        const api = TestBed.inject(MEDIA_STACK_API) as MockMediaStackApi;
        expect(api.latencyMs).toBe(0);
      });
    });

    it('ignores negative latency values silently', async () => {
      await withMockLocation('?latency=-100', () => {
        TestBed.configureTestingModule({
          providers: [...provideMediaStackApi()],
        });
        const api = TestBed.inject(MEDIA_STACK_API) as MockMediaStackApi;
        expect(api.latencyMs).toBe(0);
      });
    });
  });

  describe('scenario URL param (demo mode)', () => {
    it('ignores missing param', () => {
      TestBed.configureTestingModule({
        providers: [...provideMediaStackApi()],
      });
      const api = TestBed.inject(MEDIA_STACK_API) as MockMediaStackApi;
      expect(api).toBeInstanceOf(MockMediaStackApi);
    });

    it('ignores unknown scenario silently', async () => {
      await withMockLocation('?scenario=downloads-unknown', () => {
        TestBed.configureTestingModule({
          providers: [...provideMediaStackApi()],
        });
        const api = TestBed.inject(MEDIA_STACK_API) as MockMediaStackApi;
        expect(api).toBeInstanceOf(MockMediaStackApi);
      });
    });

    it('applies paused scenario from URL in demo mode', async () => {
      await withMockLocation('?scenario=downloads-paused', async () => {
        TestBed.configureTestingModule({
          providers: [...provideMediaStackApi()],
        });
        const api = TestBed.inject(MEDIA_STACK_API) as MockMediaStackApi;
        api.latencyMs = 0;
        const torrents = await api.listTorrents();
        expect(torrents.every((t) => t.state === 'paused')).toBe(true);
      });
    });

    it('ignores scenario param in live mode', async () => {
      const previous = environment.useLiveApi;
      (environment as { useLiveApi: boolean }).useLiveApi = true;

      await withMockLocation('?scenario=downloads-empty', () => {
        TestBed.configureTestingModule({
          providers: [provideHttpClient(), ...provideMediaStackApi()],
        });
        expect(TestBed.inject(MEDIA_STACK_API)).toBeInstanceOf(HttpMediaStackApi);
      });

      (environment as { useLiveApi: boolean }).useLiveApi = previous;
    });
  });
});

describe('applyServiceLinkBases', () => {
  it('overwrites injectable holders from API payload and strips trailing slashes', () => {
    const service = {
      jellyfin: 'http://localhost:8096',
      sonarr: 'http://localhost:8989',
      radarr: 'http://localhost:7878',
      prowlarr: 'http://localhost:9696',
      qbittorrent: 'http://127.0.0.1:8081',
      bazarr: 'http://localhost:6767',
    };
    const jellyfin = { jellyfinBase: 'http://localhost:8096' };
    const calendar = {
      sonarrBase: 'http://localhost:8989',
      radarrBase: 'http://localhost:7878',
    };

    applyServiceLinkBases(
      {
        jellyfin: 'http://localhost:18096/',
        sonarr: 'http://localhost:18989/',
        radarr: 'http://localhost:17878/',
        prowlarr: 'http://localhost:19696/',
        qbittorrent: 'http://127.0.0.1:18081/',
        bazarr: 'http://localhost:16767/',
      },
      service,
      jellyfin,
      calendar,
    );

    expect(service).toEqual({
      jellyfin: 'http://localhost:18096',
      sonarr: 'http://localhost:18989',
      radarr: 'http://localhost:17878',
      prowlarr: 'http://localhost:19696',
      qbittorrent: 'http://127.0.0.1:18081',
      bazarr: 'http://localhost:16767',
    });
    expect(jellyfin).toEqual({ jellyfinBase: 'http://localhost:18096' });
    expect(calendar).toEqual({
      sonarrBase: 'http://localhost:18989',
      radarrBase: 'http://localhost:17878',
    });
  });

  it('ignores blank values so environment fallbacks remain', () => {
    const service = { jellyfin: 'http://localhost:8096', sonarr: 'http://localhost:8989' };
    const jellyfin = { jellyfinBase: 'http://localhost:8096' };
    const calendar = { sonarrBase: 'http://localhost:8989', radarrBase: 'http://localhost:7878' };

    applyServiceLinkBases({ jellyfin: '  ', sonarr: undefined }, service, jellyfin, calendar);

    expect(service.jellyfin).toBe('http://localhost:8096');
    expect(jellyfin.jellyfinBase).toBe('http://localhost:8096');
  });
});

describe('provideOperationalLinkBases', () => {
  afterEach(() => {
    TestBed.resetTestingModule();
  });

  it('provides jellyfin, calendar, and service link bases from the environment', () => {
    TestBed.configureTestingModule({
      providers: [...provideOperationalLinkBases()],
    });

    expect(TestBed.inject(JELLYFIN_LINK_BASES)).toEqual({ jellyfinBase: environment.jellyfinBase });
    expect(TestBed.inject(CALENDAR_LINK_BASES)).toEqual({
      sonarrBase: environment.sonarrBase,
      radarrBase: environment.radarrBase,
    });
    expect(TestBed.inject(SERVICE_LINK_BASES)).toEqual({
      jellyfin: environment.jellyfinBase,
      sonarr: environment.sonarrBase,
      radarr: environment.radarrBase,
      prowlarr: environment.prowlarrBase,
      qbittorrent: environment.qbittorrentBase,
      bazarr: environment.bazarrBase,
    });
  });

  it('Live mode loads Compose host ports from /service-links before bootstrap finishes', async () => {
    const previous = environment.useLiveApi;
    (environment as { useLiveApi: boolean }).useLiveApi = true;

    try {
      TestBed.configureTestingModule({
        providers: [
          provideHttpClient(),
          provideHttpClientTesting(),
          ...provideOperationalLinkBases(),
        ],
      });

      const httpMock = TestBed.inject(HttpTestingController);
      const initStatus = TestBed.inject(ApplicationInitStatus);
      const initDone = initStatus.donePromise;

      const req = httpMock.expectOne('/api/service-links');
      expect(req.request.method).toBe('GET');
      req.flush({
        jellyfin: 'http://localhost:18096',
        sonarr: 'http://localhost:18989',
        radarr: 'http://localhost:17878',
        prowlarr: 'http://localhost:19696',
        qbittorrent: 'http://127.0.0.1:18081',
        bazarr: 'http://localhost:16767',
      });

      await initDone;

      expect(TestBed.inject(JELLYFIN_LINK_BASES)).toEqual({ jellyfinBase: 'http://localhost:18096' });
      expect(TestBed.inject(CALENDAR_LINK_BASES)).toEqual({
        sonarrBase: 'http://localhost:18989',
        radarrBase: 'http://localhost:17878',
      });
      expect(TestBed.inject(SERVICE_LINK_BASES)).toEqual({
        jellyfin: 'http://localhost:18096',
        sonarr: 'http://localhost:18989',
        radarr: 'http://localhost:17878',
        prowlarr: 'http://localhost:19696',
        qbittorrent: 'http://127.0.0.1:18081',
        bazarr: 'http://localhost:16767',
      });
      httpMock.verify();
    } finally {
      (environment as { useLiveApi: boolean }).useLiveApi = previous;
    }
  });
});

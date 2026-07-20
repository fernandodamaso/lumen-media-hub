import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';

import { environment } from '../../environments/environment';
import { CALENDAR_LINK_BASES } from '../calendar/calendar.models';
import { JELLYFIN_LINK_BASES } from '../library/library.models';
import { MEDIA_STACK_API } from './media-stack-api';
import { HttpMediaStackApi } from './http-media-stack-api';
import { MockMediaStackApi } from './mock-media-stack-api';
import {
  SERVICE_LINK_BASES,
  provideMediaStackApi,
  provideOperationalLinkBases,
} from './media-stack-api.providers';

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
      const binding = provideMediaStackApi()[0] as { useClass: unknown };
      expect(binding.useClass).toBe(HttpMediaStackApi);

      TestBed.configureTestingModule({
        providers: [provideHttpClient(), ...provideMediaStackApi()],
      });
      expect(TestBed.inject(MEDIA_STACK_API)).toBeInstanceOf(HttpMediaStackApi);
    } finally {
      (environment as { useLiveApi: boolean }).useLiveApi = previous;
    }
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
});

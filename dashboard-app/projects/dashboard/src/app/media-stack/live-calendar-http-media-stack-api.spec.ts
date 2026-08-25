import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { environment } from '../../environments/environment';
import { LiveCalendarHttpMediaStackApi } from './live-calendar-http-media-stack-api';

describe('LiveCalendarHttpMediaStackApi', () => {
  let api: LiveCalendarHttpMediaStackApi;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        LiveCalendarHttpMediaStackApi,
      ],
    });
    api = TestBed.inject(LiveCalendarHttpMediaStackApi);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    http.verify();
  });

  it('loads the neutral combined calendar and preserves source health and provider identity', async () => {
    const pending = api.listCalendarEvents();
    const request = http.expectOne(`${environment.apiBaseUrl.replace(/\/$/, '')}/calendar`);
    expect(request.request.method).toBe('GET');
    request.flush({
      ok: true,
      generatedAt: '2026-08-25T10:00:00Z',
      sources: { sonarr: 'error', radarr: 'ok' },
      events: [
        {
          id: 'radarr:movie:22',
          kind: 'movie',
          movieId: 22,
          titleSlug: 'dune-2021',
          title: 'Dune',
          additional: 'Digital release',
          date: 'Aug 26',
          airDate: '2026-08-26T10:00:00Z',
          monitored: true,
          hasFile: false,
        },
      ],
    });

    const events = await pending;
    expect(events[0]).toMatchObject({
      id: 'radarr:movie:22',
      kind: 'movie',
      movieId: 22,
      titleSlug: 'dune-2021',
    });
    expect(events.sources).toEqual({ sonarr: 'error', radarr: 'ok' });
    expect(events.generatedAt).toBe('2026-08-25T10:00:00Z');
  });

  it('rejects mixed events whose provider-specific identity does not match kind', async () => {
    const pending = api.listCalendarEvents();
    http.expectOne(`${environment.apiBaseUrl.replace(/\/$/, '')}/calendar`).flush({
      ok: true,
      sources: { sonarr: 'ok', radarr: 'ok' },
      events: [
        {
          id: 'radarr:movie:22',
          kind: 'movie',
          episodeId: 22,
          title: 'Dune',
          additional: 'Digital release',
          date: 'Aug 26',
          airDate: '2026-08-26T10:00:00Z',
        },
      ],
    });

    await expect(pending).rejects.toThrow(/movieId/);
  });
});
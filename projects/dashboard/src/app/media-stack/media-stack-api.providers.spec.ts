import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';

import { environment } from '../../environments/environment';
import { MEDIA_STACK_API } from './media-stack-api';
import { HttpMediaStackApi } from './http-media-stack-api';
import { MockMediaStackApi } from './mock-media-stack-api';
import { provideMediaStackApi } from './media-stack-api.providers';
import { provideMediaStackApi as provideMediaStackApiPages } from './media-stack-api.providers.pages';

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

  it('Pages providers always bind MockMediaStackApi', () => {
    TestBed.configureTestingModule({
      providers: [...provideMediaStackApiPages()],
    });

    expect(TestBed.inject(MEDIA_STACK_API)).toBeInstanceOf(MockMediaStackApi);
  });
});

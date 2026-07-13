import { ApplicationConfig, provideBrowserGlobalErrorListeners, provideZoneChangeDetection } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { provideRouter, withEnabledBlockingInitialNavigation } from '@angular/router';

import { environment } from '../environments/environment';
import { routes } from './app.routes';
import {
  CALENDAR_LINK_BASES,
  JELLYFIN_LINK_BASES,
  MEDIA_STACK_API,
} from './downloads/media-stack-api';
import { HttpMediaStackApi } from './downloads/http-media-stack-api';
import { MockMediaStackApi } from './downloads/mock-media-stack-api';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(routes, withEnabledBlockingInitialNavigation()),
    provideHttpClient(),
    {
      provide: MEDIA_STACK_API,
      useClass: environment.useLiveApi ? HttpMediaStackApi : MockMediaStackApi,
    },
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
  ],
};

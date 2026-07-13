import { ApplicationConfig, provideBrowserGlobalErrorListeners, provideZoneChangeDetection } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { provideRouter, withEnabledBlockingInitialNavigation } from '@angular/router';

import { routes } from './app.routes';
import { CALENDAR_LINK_BASES, DEFAULT_CALENDAR_LINK_BASES } from './downloads/media-stack-api';
import { provideMediaStackApi } from './downloads/media-stack-api.providers';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(routes, withEnabledBlockingInitialNavigation()),
    provideHttpClient(),
    ...provideMediaStackApi(),
    { provide: CALENDAR_LINK_BASES, useValue: { ...DEFAULT_CALENDAR_LINK_BASES } },
  ],
};

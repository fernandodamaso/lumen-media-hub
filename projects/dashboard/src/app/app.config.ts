import { ApplicationConfig, provideBrowserGlobalErrorListeners, provideZoneChangeDetection } from '@angular/core';
import { provideRouter, withEnabledBlockingInitialNavigation } from '@angular/router';

import { routes } from './app.routes';
import { CALENDAR_LINK_BASES, DEFAULT_CALENDAR_LINK_BASES, MEDIA_STACK_API } from './downloads/media-stack-api';
import { MockMediaStackApi } from './downloads/mock-media-stack-api';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(routes, withEnabledBlockingInitialNavigation()),
    { provide: MEDIA_STACK_API, useClass: MockMediaStackApi },
    { provide: CALENDAR_LINK_BASES, useValue: { ...DEFAULT_CALENDAR_LINK_BASES } },
  ],
};

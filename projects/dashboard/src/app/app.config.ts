import { ApplicationConfig, provideBrowserGlobalErrorListeners, provideZoneChangeDetection } from '@angular/core';
import { provideRouter, withEnabledBlockingInitialNavigation } from '@angular/router';

import { routes } from './app.routes';
import { MEDIA_STACK_API } from './downloads/media-stack-api';
import { MockMediaStackApi } from './downloads/mock-media-stack-api';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(routes, withEnabledBlockingInitialNavigation()),
    { provide: MEDIA_STACK_API, useClass: MockMediaStackApi },
  ],
};

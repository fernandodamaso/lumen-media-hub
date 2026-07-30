import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideHttpClient } from '@angular/common/http';
import { provideRouter } from '@angular/router';

import { routes } from './app.routes';
import { ActivityFacade } from './right-rail/activity.facade';
import { AutomationFacade } from './automation/automation.facade';
import { CalendarFacade } from './calendar/calendar.facade';
import { DownloadsFacade } from './downloads/downloads.facade';
import { LibraryStatsFacade } from './library/library-stats.facade';
import { StorageFacade } from './storage/storage.facade';
import { provideMediaStackApi, provideOperationalLinkBases } from './media-stack/media-stack-api.providers';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes),
    provideHttpClient(),
    ...provideMediaStackApi(),
    ...provideOperationalLinkBases(),
    CalendarFacade,
    DownloadsFacade,
    LibraryStatsFacade,
    StorageFacade,
    AutomationFacade,
    ActivityFacade,
  ],
};

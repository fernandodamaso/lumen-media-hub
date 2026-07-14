import { Provider } from '@angular/core';

import { environment } from '../../environments/environment';
import { CALENDAR_LINK_BASES } from '../calendar/calendar.models';
import { JELLYFIN_LINK_BASES } from '../library/library.models';
import { MEDIA_STACK_API } from './media-stack-api';
import { MockMediaStackApi } from './mock-media-stack-api';

/**
 * Pages / static showcase providers: mock API only.
 * Intentionally omits HttpMediaStackApi so live `/api` client code is not bundled.
 */
export function provideMediaStackApi(): Provider[] {
  return [{ provide: MEDIA_STACK_API, useClass: MockMediaStackApi }];
}

export function provideOperationalLinkBases(): Provider[] {
  return [
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
  ];
}

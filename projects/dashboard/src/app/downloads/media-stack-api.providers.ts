import { Provider } from '@angular/core';

import { environment } from '../../environments/environment';
import { MEDIA_STACK_API } from './media-stack-api';
import { HttpMediaStackApi } from './http-media-stack-api';
import { MockMediaStackApi } from './mock-media-stack-api';

/** Bind MediaStackApi to mock (default) or HTTP adapter when live env is selected. */
export function provideMediaStackApi(): Provider[] {
  return [
    {
      provide: MEDIA_STACK_API,
      useClass: environment.useLiveApi ? HttpMediaStackApi : MockMediaStackApi,
    },
  ];
}

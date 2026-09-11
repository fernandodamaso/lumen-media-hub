import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { firstValueFrom, fromEvent, takeUntil } from 'rxjs';

import { environment } from '../../environments/environment';
import { CleanupPreview, CleanupPreviewRequest } from '../storage/cleanup.models';
import { requireCleanupPreview } from '../storage/cleanup-response';
import { isRecord } from './http-response';
import { LiveCalendarHttpMediaStackApi } from './live-calendar-http-media-stack-api';

@Injectable()
export class StorageGuardianHttpMediaStackApi extends LiveCalendarHttpMediaStackApi {
  private readonly cleanupHttp = inject(HttpClient);
  private readonly cleanupBase = environment.apiBaseUrl.replace(/\/$/, '');

  override async previewStorageCleanup(
    policy: CleanupPreviewRequest,
    signal?: AbortSignal,
  ): Promise<CleanupPreview> {
    if (signal?.aborted) throw abortError();
    try {
      const request = this.cleanupHttp.post<unknown>(`${this.cleanupBase}/storage/cleanup-preview`, policy);
      const raw = await firstValueFrom(signal ? request.pipe(takeUntil(fromEvent(signal, 'abort'))) : request);
      const preview = requireCleanupPreview(raw);
      if (preview.storage.targetFreeBytes !== policy.targetFreeBytes) {
        throw new Error('Malformed cleanup preview: target does not match request');
      }
      return preview;
    } catch (error: unknown) {
      if (signal?.aborted) throw abortError();
      if (error instanceof HttpErrorResponse && isRecord(error.error)) {
        const message = error.error['error'];
        if (typeof message === 'string' && message.trim() && !/[\\/]/.test(message)) {
          throw new Error(message.trim());
        }
      }
      throw error instanceof Error ? error : new Error('POST /storage/cleanup-preview failed');
    }
  }
}

function abortError(): DOMException {
  return new DOMException('The operation was aborted.', 'AbortError');
}

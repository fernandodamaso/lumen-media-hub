import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  effect,
  inject,
  input,
  model,
  output,
  signal,
} from '@angular/core';

import { MEDIA_STACK_API } from '../../media-stack/media-stack-api';
import { MmButton, MmCheckbox, MmDialog, MmToastService } from '../../ui';
import { RequestableMediaItem, TvSeason } from '../media-request.models';

export interface MediaRequestCompletion {
  identity: string;
  requestId: number;
  status: 'requested' | 'processing';
  alreadyRequested: boolean;
}

@Component({
  selector: 'mm-media-request-dialog',
  imports: [MmButton, MmCheckbox, MmDialog],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './media-request-dialog.html',
  styleUrl: './media-request-dialog.scss',
})
export class MediaRequestDialog {
  private readonly api = inject(MEDIA_STACK_API);
  private readonly toast = inject(MmToastService);
  private readonly destroyRef = inject(DestroyRef);

  readonly item = input.required<RequestableMediaItem>();
  readonly opened = model(false);
  readonly completed = output<MediaRequestCompletion>();
  readonly busy = signal(false);
  readonly loadingSeasons = signal(false);
  readonly seasons = signal<TvSeason[]>([]);
  readonly selectedSeasonNumbers = signal<ReadonlySet<number>>(new Set());
  readonly feedback = signal<string | null>(null);
  readonly canSubmit = computed(() => {
    if (this.busy() || this.loadingSeasons()) return false;
    return this.item().type === 'movie' || this.selectedSeasonNumbers().size > 0;
  });

  private seasonRequest: AbortController | null = null;
  private loadGeneration = 0;
  private activeOpenIdentity: string | null = null;

  constructor() {
    effect(() => {
      const opened = this.opened();
      const item = this.item();
      if (!opened) {
        this.activeOpenIdentity = null;
        this.cancelSeasonLoad();
        return;
      }
      if (this.activeOpenIdentity === item.identity) return;
      this.activeOpenIdentity = item.identity;
      this.resetState();
      if (item.type === 'tv') {
        void this.loadTvSeasons(item.tmdbId);
      }
    });
    this.destroyRef.onDestroy(() => {
      this.cancelSeasonLoad();
    });
  }

  setOpened(opened: boolean): void {
    this.opened.set(opened);
  }

  close(): void {
    this.opened.set(false);
  }

  isSeasonSelected(seasonNumber: number): boolean {
    return this.selectedSeasonNumbers().has(seasonNumber);
  }

  setSeasonSelected(seasonNumber: number, selected: boolean): void {
    this.selectedSeasonNumbers.update((current) => {
      const next = new Set(current);
      if (selected) next.add(seasonNumber);
      else next.delete(seasonNumber);
      return next;
    });
  }

  async submit(): Promise<void> {
    if (!this.canSubmit()) return;
    this.busy.set(true);
    this.feedback.set(null);
    const item = this.item();
    const seasons = [...this.selectedSeasonNumbers()].sort((left, right) => left - right);
    try {
      const action = await this.api.requestMedia({
        mediaType: item.type,
        mediaId: item.tmdbId,
        ...(item.hermesId ? { hermesId: item.hermesId } : {}),
        ...(item.type === 'tv' ? { seasons } : {}),
      });
      if (
        !action.ok ||
        !action.jellyseerr_request_id ||
        !action.request_status ||
        typeof action.already_requested !== 'boolean'
      ) {
        this.feedback.set('This request could not be completed. Try again.');
        return;
      }
      this.opened.set(false);
      this.toast.show('Request submitted', {
        body: action.message,
        tone: 'success',
      });
      this.completed.emit({
        identity: item.identity,
        requestId: action.jellyseerr_request_id,
        status: action.request_status,
        alreadyRequested: action.already_requested,
      });
    } catch {
      this.feedback.set('This request could not be completed. Try again.');
    } finally {
      this.busy.set(false);
    }
  }

  private resetState(): void {
    this.cancelSeasonLoad();
    this.seasons.set([]);
    this.selectedSeasonNumbers.set(new Set());
    this.feedback.set(null);
    this.busy.set(false);
  }

  private async loadTvSeasons(tmdbId: number): Promise<void> {
    const controller = new AbortController();
    this.seasonRequest = controller;
    const generation = ++this.loadGeneration;
    this.loadingSeasons.set(true);
    try {
      const collection = await this.api.getTvSeasons(tmdbId, controller.signal);
      if (controller.signal.aborted || generation !== this.loadGeneration) return;
      const seasons = [...collection.seasons].sort(
        (left, right) => left.seasonNumber - right.seasonNumber,
      );
      this.seasons.set(seasons);
      this.selectedSeasonNumbers.set(
        new Set(seasons.filter((season) => season.seasonNumber > 0).map((season) => season.seasonNumber)),
      );
    } catch {
      if (!controller.signal.aborted && generation === this.loadGeneration) {
        this.feedback.set('Seasons could not be loaded. Try again.');
      }
    } finally {
      if (generation === this.loadGeneration) {
        this.loadingSeasons.set(false);
        this.seasonRequest = null;
      }
    }
  }

  private cancelSeasonLoad(): void {
    this.loadGeneration += 1;
    this.seasonRequest?.abort();
    this.seasonRequest = null;
    this.loadingSeasons.set(false);
  }
}

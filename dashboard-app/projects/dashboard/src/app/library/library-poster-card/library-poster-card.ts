import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  input,
  signal,
} from '@angular/core';
import { LucideEye, LucideEyeOff, LucidePlay, LucideTrash2 } from '@lucide/angular';
import { MmButton, MmDialog, MmIconButton, MmMediaCard, MmPosterActionOverlay, MmToastService } from '@app/ui';
import {
  DEFAULT_LIBRARY_ART,
  formatLibraryDeleteDialogCopy,
  formatLibraryDeleteToasts,
  LibraryDeletePreview,
  LibraryItem,
} from '../library.models';
import { LibraryItemsFacade } from '../library-items.facade';

@Component({
  selector: 'mm-library-poster-card',
  imports: [
    MmMediaCard,
    MmIconButton,
    MmPosterActionOverlay,
    MmDialog,
    MmButton,
    LucideEye,
    LucideEyeOff,
    LucidePlay,
    LucideTrash2,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './library-poster-card.html',
  styleUrl: './library-poster-card.scss',
})
export class LibraryPosterCard {
  private readonly facade = inject(LibraryItemsFacade);
  private readonly toast = inject(MmToastService);

  readonly item = input.required<LibraryItem>();
  readonly href = input<string | null>(null);
  readonly detailsHref = input<string | null>(null);
  readonly retryToken = input<unknown>(null);

  readonly watchedBusy = signal(false);
  readonly previewBusy = signal(false);
  readonly deleteBusy = signal(false);
  readonly dialogOpen = signal(false);
  readonly directDialogOpen = signal(false);
  readonly directDeleteTitle = signal('');
  private readonly preview = signal<LibraryDeletePreview | null>(null);

  readonly dialogCopy = computed(() => {
    const current = this.preview();
    return current ? formatLibraryDeleteDialogCopy(current) : null;
  });

  readonly imageUrl = computed(() => {
    const current = this.item();
    if (current.artworkState !== 'ok') return null;
    const art = current.art.trim();
    const urlMatch = /^url\(["']?([^"')]+)["']?\)/.exec(art);
    if (urlMatch?.[1]) return urlMatch[1];
    if (art.startsWith('http://') || art.startsWith('https://')) return art;
    return null;
  });

  readonly fallbackArt = computed(() => {
    const current = this.item();
    if (current.artworkState !== 'ok' || this.imageUrl()) return DEFAULT_LIBRARY_ART;
    return current.art || DEFAULT_LIBRARY_ART;
  });

  async onToggleWatched(event: MouseEvent): Promise<void> {
    event.preventDefault();
    event.stopPropagation();
    if (this.watchedBusy()) return;
    const current = this.item();
    this.watchedBusy.set(true);
    try {
      const nextPlayed = !current.played;
      await this.facade.setPlayed(current.id, nextPlayed);
      this.toast.show(nextPlayed ? 'Marked as watched' : 'Marked as unwatched', { tone: 'success' });
    } catch {
      this.toast.show('Could not update watched state', { tone: 'error' });
    } finally {
      this.watchedBusy.set(false);
    }
  }

  async onDelete(event: MouseEvent): Promise<void> {
    event.preventDefault();
    event.stopPropagation();
    if (this.previewBusy() || this.deleteBusy()) return;
    this.previewBusy.set(true);
    try {
      const preview = await this.facade.previewDeletion(this.item().id);
      this.preview.set(preview);
      this.dialogOpen.set(true);
    } catch (error) {
      if (this.isUnmanagedTitleError(error)) {
        const title = this.extractUnmanagedTitle(error);
        this.directDeleteTitle.set(title || this.item().title);
        this.directDialogOpen.set(true);
        return;
      }
      this.toast.show('Could not prepare deletion', { tone: 'error' });
    } finally {
      this.previewBusy.set(false);
    }
  }

  cancelDelete(): void {
    if (this.deleteBusy()) return;
    this.dialogOpen.set(false);
    this.preview.set(null);
  }

  async confirmDelete(): Promise<void> {
    const currentPreview = this.preview();
    if (!currentPreview || this.deleteBusy()) return;
    this.deleteBusy.set(true);
    try {
      const result = await this.facade.deleteItem(this.item().id, currentPreview.previewId);
      for (const toast of formatLibraryDeleteToasts(result, currentPreview)) {
        this.toast.show(toast.title, { body: toast.body, tone: toast.tone });
      }
      this.dialogOpen.set(false);
      this.preview.set(null);
    } catch {
      this.toast.show('Could not delete this title', { tone: 'error' });
      this.dialogOpen.set(false);
      this.preview.set(null);
    } finally {
      this.deleteBusy.set(false);
    }
  }

  private isUnmanagedTitleError(error: unknown): boolean {
    const code = (error as { code?: unknown } | null)?.['code'];
    return code === 'unmanaged_title';
  }

  private extractUnmanagedTitle(error: unknown): string {
    const title = (error as { title?: unknown } | null)?.['title'];
    return typeof title === 'string' && title.trim() ? title : '';
  }

  cancelDirectDelete(): void {
    if (this.deleteBusy()) return;
    this.directDialogOpen.set(false);
  }

  async confirmDirectDelete(): Promise<void> {
    if (this.deleteBusy()) return;
    this.deleteBusy.set(true);
    try {
      await this.facade.deleteItemDirectly(this.item().id);
      this.toast.show('Removed from Jellyfin. Torrents and files were not touched.', { tone: 'success' });
      this.directDialogOpen.set(false);
    } catch {
      this.toast.show('Could not delete this title from Jellyfin', { tone: 'error' });
      this.directDialogOpen.set(false);
    } finally {
      this.deleteBusy.set(false);
    }
  }
}

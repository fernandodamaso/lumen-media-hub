import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { LucideDownload, LucideFolder, LucideHardDrive, LucideLayers } from '@lucide/angular';
import { MmButton, MmCard, MmSkeleton, MmStateCard } from '@app/ui';
import { StorageFacade } from '../storage/storage.facade';
import { StorageVolume, StorageVolumeKind } from '../storage/storage.models';
import { formatStorageBytes, STORAGE_VOLUME_BAR_COLOR } from '../storage/storage-format';

@Component({
  selector: 'mm-storage-card',
  imports: [MmButton, MmCard, MmSkeleton, MmStateCard, LucideHardDrive, LucideFolder, LucideDownload, LucideLayers],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './storage-card.html',
  styleUrl: './storage-card.scss',
})
export class StorageCard {
  readonly facade = inject(StorageFacade);
  readonly skeletonRows = [0, 1, 2];
  readonly formatBytes = formatStorageBytes;

  constructor() {
    this.facade.startPolling();
  }

  percent(volume: StorageVolume): number {
    if (!volume.totalBytes) return 0;
    return Math.min(100, Math.round((volume.usedBytes / volume.totalBytes) * 100));
  }

  barColor(kind: StorageVolumeKind): string {
    return STORAGE_VOLUME_BAR_COLOR[kind];
  }

  retry(): void {
    void this.facade.refresh();
  }
}

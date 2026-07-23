import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { LucideDownload, LucideFolder, LucideHardDrive, LucideLayers } from '@lucide/angular';
import { MmButton, MmCard, MmProgress, MmSkeleton, MmStateCard, MmStatus } from '@app/ui';
import { StorageFacade } from '../storage/storage.facade';
import { StorageVolume, StorageVolumeKind } from '../storage/storage.models';
import { formatStorageBytes, STORAGE_VOLUME_TONE, StorageVolumeTone } from '../storage/storage-format';

@Component({
  selector: 'mm-storage-card',
  imports: [MmButton, MmCard, MmProgress, MmSkeleton, MmStateCard, MmStatus, LucideHardDrive, LucideFolder, LucideDownload, LucideLayers],
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

  barTone(kind: StorageVolumeKind): StorageVolumeTone {
    return STORAGE_VOLUME_TONE[kind];
  }

  retry(): void {
    void this.facade.refresh({ initial: true });
  }
}

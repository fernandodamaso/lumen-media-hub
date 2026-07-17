export type StorageVolumeKind = 'library' | 'downloads' | 'cache';

export interface StorageVolume {
  id: string;
  label: string;
  kind: StorageVolumeKind;
  usedBytes: number;
  totalBytes: number;
}

export interface StorageOverview {
  generatedAt: string;
  volumes: StorageVolume[];
}

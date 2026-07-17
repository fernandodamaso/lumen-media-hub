import { StorageOverview, StorageVolume, StorageVolumeKind } from './storage.models';
import { MediaStackStorageOverviewDto, MediaStackStorageVolumeDto } from '../media-stack/wire/storage';

const STORAGE_VOLUME_KINDS: StorageVolumeKind[] = ['library', 'downloads', 'cache'];

export const mapStorageOverview = (dto: MediaStackStorageOverviewDto): StorageOverview => ({
  generatedAt: dto.generatedAt ?? '',
  volumes: (dto.volumes ?? []).map(mapStorageVolume),
});

const mapStorageVolume = (volume: MediaStackStorageVolumeDto): StorageVolume => ({
  id: volume.id?.trim() || 'unknown',
  label: volume.label?.trim() || 'Unnamed volume',
  kind: normalizeStorageVolumeKind(volume.kind),
  usedBytes: normalizeBytes(volume.usedBytes),
  totalBytes: normalizeBytes(volume.totalBytes),
});

function normalizeStorageVolumeKind(kind: string | undefined): StorageVolumeKind {
  const normalized = kind?.trim().toLowerCase() ?? '';
  return STORAGE_VOLUME_KINDS.includes(normalized as StorageVolumeKind)
    ? (normalized as StorageVolumeKind)
    : 'cache';
}

function normalizeBytes(value: number | undefined): number {
  return typeof value === 'number' && Number.isFinite(value) ? Math.max(0, value) : 0;
}

export function formatStorageBytes(bytes: number): string {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** index;
  return `${index >= 3 ? value.toFixed(1) : value.toFixed(index ? 0 : 0)} ${units[index]}`;
}

export const STORAGE_VOLUME_ICON: Record<StorageVolumeKind, string> = {
  library: 'folder',
  downloads: 'download',
  cache: 'layers',
};

export const STORAGE_VOLUME_BAR_COLOR: Record<StorageVolumeKind, string> = {
  library: 'var(--mm-component-premiere)',
  downloads: 'var(--mm-component-info)',
  cache: 'var(--mm-component-accent)',
};

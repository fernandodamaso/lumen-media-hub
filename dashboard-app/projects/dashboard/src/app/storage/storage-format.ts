import { StorageOverview, StorageVolume, StorageVolumeKind } from './storage.models';
import { MediaStackStorageOverviewDto, MediaStackStorageVolumeDto } from '../media-stack/wire/storage';

const STORAGE_VOLUME_KINDS: StorageVolumeKind[] = ['library', 'downloads', 'cache'];

export const mapStorageOverview = (dto: MediaStackStorageOverviewDto): StorageOverview => ({
  generatedAt: dto.generatedAt ?? '',
  volumes: (dto.volumes ?? []).map(mapStorageVolume),
});

const mapStorageVolume = (volume: MediaStackStorageVolumeDto): StorageVolume => {
  const id = volume.id.trim();
  const label = volume.label.trim();
  if (!id) {
    throw new Error('Malformed storage volume: missing id');
  }
  if (!label) {
    throw new Error('Malformed storage volume: missing label');
  }
  if (typeof volume.usedBytes !== 'number' || !Number.isFinite(volume.usedBytes)) {
    throw new Error('Malformed storage volume: missing usedBytes');
  }
  if (typeof volume.totalBytes !== 'number' || !Number.isFinite(volume.totalBytes)) {
    throw new Error('Malformed storage volume: missing totalBytes');
  }
  return {
    id,
    label,
    kind: normalizeStorageVolumeKind(volume.kind),
    usedBytes: Math.max(0, volume.usedBytes),
    totalBytes: Math.max(0, volume.totalBytes),
  };
};

function normalizeStorageVolumeKind(kind: string | undefined): StorageVolumeKind {
  const normalized = kind?.trim().toLowerCase() ?? '';
  return STORAGE_VOLUME_KINDS.includes(normalized as StorageVolumeKind)
    ? (normalized as StorageVolumeKind)
    : 'cache';
}

export function formatStorageBytes(bytes: number): string {
  if (!bytes) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** index;
  return `${index >= 3 ? value.toFixed(1) : value.toFixed(0)} ${units[index]}`;
}

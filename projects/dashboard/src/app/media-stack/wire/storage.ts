/** Raw storage-overview payload from GET /storage/overview stays behind this boundary. */
export interface MediaStackStorageVolumeDto {
  id: string;
  label: string;
  kind?: string;
  usedBytes?: number;
  totalBytes?: number;
}

export interface MediaStackStorageOverviewDto {
  ok?: boolean;
  generatedAt?: string;
  volumes?: MediaStackStorageVolumeDto[] | null;
  error?: string;
}

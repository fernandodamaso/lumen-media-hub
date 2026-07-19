/** Raw storage-overview payload from GET /storage/overview stays behind this boundary. */
export interface MediaStackStorageVolumeDto {
  id: string;
  label: string;
  kind?: string;
  /** Required finite capacities — zero is valid empty, missing is not. */
  usedBytes: number;
  totalBytes: number;
}

export interface MediaStackStorageOverviewDto {
  ok?: boolean;
  generatedAt?: string;
  volumes?: MediaStackStorageVolumeDto[] | null;
  error?: string;
}

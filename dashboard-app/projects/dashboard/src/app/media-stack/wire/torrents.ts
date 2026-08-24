/** Raw qBittorrent-shaped data stays behind this boundary. */
export interface MediaStackTorrentDto {
  hash: string;
  name: string;
  state: string;
  progress: number;
  size: number;
  downloaded: number;
  dlspeed: number;
  upspeed: number;
  eta: number;
  category?: string;
  completionOn: number | null;
}

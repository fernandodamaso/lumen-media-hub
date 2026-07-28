/** Keep in sync with watch-next-grid.scss @container breakpoints. */
export function resolveWatchNextPageSize(width: number): number {
  if (width <= 0) return 5;
  if (width <= 520) return 2;
  if (width <= 720) return 3;
  if (width <= 900) return 4;
  return 5;
}

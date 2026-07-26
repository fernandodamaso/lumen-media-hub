import { WritableSignal } from '@angular/core';

export function applyLibraryLoadFailure(options: {
  initial: boolean;
  status: WritableSignal<string>;
  error: WritableSignal<string>;
  clearOnInitial: () => void;
  hasPriorData: boolean;
  refreshError: string;
  loadError: string;
}): void {
  if (!options.initial && options.hasPriorData) {
    options.error.set(options.refreshError);
    return;
  }
  options.status.set('error');
  options.error.set(options.loadError);
  if (options.initial) options.clearOnInitial();
}

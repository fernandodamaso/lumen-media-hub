import type { MediaStackApi } from '../app/media-stack/media-stack-api';

export const mediaStackLibraryMutationStub: Pick<
  MediaStackApi,
  'setLibraryItemPlayed' | 'previewLibraryItemDeletion' | 'deleteLibraryItem'
> = {
  setLibraryItemPlayed: (_id, played) => Promise.resolve({ played }),
  previewLibraryItemDeletion: () => Promise.reject(new Error('not implemented')),
  deleteLibraryItem: () =>
    Promise.resolve({
      ok: false,
      removed: false,
      torrentCount: 0,
      partial: true,
      error: 'Unable to finish deletion',
    }),
};

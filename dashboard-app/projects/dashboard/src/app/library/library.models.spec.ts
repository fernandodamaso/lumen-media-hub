import { resolveJellyfinItemLink } from './library.models';

describe('library.models', () => {
  it('resolves Jellyfin detail links when configured and playable', () => {
    expect(
      resolveJellyfinItemLink({ id: 'jf-dune', playable: true }, { jellyfinBase: 'http://localhost:8096/' }),
    ).toBe('http://localhost:8096/web/index.html#!/details?id=jf-dune');
    expect(resolveJellyfinItemLink({ id: 'jf-dune', playable: false })).toBeNull();
    expect(resolveJellyfinItemLink({ id: '', playable: true })).toBeNull();
    expect(resolveJellyfinItemLink({ id: 'unknown', playable: true })).toBeNull();
  });

  it('disables Jellyfin detail links when the base is empty', () => {
    expect(resolveJellyfinItemLink({ id: 'jf-dune', playable: true }, { jellyfinBase: '' })).toBeNull();
    expect(resolveJellyfinItemLink({ id: 'jf-dune', playable: true }, {})).toBeNull();
  });
});

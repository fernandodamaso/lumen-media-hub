import { mapStorageOverview } from './storage-format';

describe('storage format / storage mapping', () => {
  it('maps a storage overview DTO into domain volumes', () => {
    const overview = mapStorageOverview({
      generatedAt: '2026-07-13T12:00:00Z',
      volumes: [
        { id: 'media-library', label: 'Media library', kind: 'library', usedBytes: 10, totalBytes: 20 },
        { id: 'downloads', label: 'Downloads', kind: 'downloads', usedBytes: 5, totalBytes: 50 },
        { id: 'cache', label: 'Cache & temp', kind: 'cache', usedBytes: 1, totalBytes: 8 },
      ],
    });
    expect(overview.generatedAt).toBe('2026-07-13T12:00:00Z');
    expect(overview.volumes.map((volume) => volume.kind)).toEqual(['library', 'downloads', 'cache']);
    expect(overview.volumes[0]).toMatchObject({ id: 'media-library', usedBytes: 10, totalBytes: 20 });
  });

  it('defaults missing fields and clamps invalid values', () => {
    const overview = mapStorageOverview({
      volumes: [
        { id: '', label: ' ', kind: 'unknown-kind', usedBytes: -5, totalBytes: Number.NaN },
      ],
    });
    expect(overview.generatedAt).toBe('');
    expect(overview.volumes[0]).toEqual({
      id: 'unknown',
      label: 'Unnamed volume',
      kind: 'cache',
      usedBytes: 0,
      totalBytes: 0,
    });
    expect(mapStorageOverview({}).volumes).toEqual([]);
  });
});

export const MOCK_POSTER = {
  series1: '/storybook-mocks/posters/neon-veil.png',
  movie1: '/storybook-mocks/posters/apothecary.png',
  movie2: '/storybook-mocks/posters/mirror-shard.png',
} as const;

export const mockArtUrl = (path: string): string => `url("${path}")`;

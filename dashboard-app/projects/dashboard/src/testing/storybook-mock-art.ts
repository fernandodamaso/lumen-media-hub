export const MOCK_POSTER = {
  series1: '/storybook-mocks/posters/series-1.svg',
  movie1: '/storybook-mocks/posters/movie-1.svg',
  movie2: '/storybook-mocks/posters/movie-2.svg',
} as const;

export const mockArtUrl = (path: string): string => `url("${path}")`;

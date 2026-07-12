import { TestBed } from '@angular/core/testing';
import { MEDIA_UI_THEMES, ThemeService } from './theme.service';

describe('ThemeService', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.dataset['theme'] = '';
    TestBed.resetTestingModule();
  });

  it('starts with the saved theme and applies it to the document', () => {
    localStorage.setItem('media-ui-theme', 'tokyo-night');
    const service = TestBed.inject(ThemeService);
    TestBed.tick();

    expect(service.theme()).toBe('tokyo-night');
    expect(document.documentElement.dataset['theme']).toBe('tokyo-night');
    expect(service.themes).toEqual(MEDIA_UI_THEMES);
  });

  it('persists only supported selections', () => {
    const service = TestBed.inject(ThemeService);

    service.setTheme('github-dark-pro');
    TestBed.tick();
    expect(service.theme()).toBe('github-dark-pro');
    expect(localStorage.getItem('media-ui-theme')).toBe('github-dark-pro');

    service.setTheme('not-a-theme' as never);
    expect(service.theme()).toBe('github-dark-pro');
  });

  it('uses the bootstrapped document theme before storage', () => {
    document.documentElement.dataset['theme'] = 'github-dark-pro';
    localStorage.setItem('media-ui-theme', 'tokyo-night');

    expect(TestBed.inject(ThemeService).theme()).toBe('github-dark-pro');
  });
});

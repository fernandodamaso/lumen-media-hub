import { TestBed } from '@angular/core/testing';
import { ThemeService } from './theme.service';

describe('ThemeService', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.dataset['theme'] = '';
    let meta = document.querySelector('meta[name="theme-color"]');
    if (!meta) {
      meta = document.createElement('meta');
      meta.setAttribute('name', 'theme-color');
      document.head.appendChild(meta);
    }
    meta.setAttribute('content', '#000000');
    TestBed.resetTestingModule();
  });

  it('starts with the saved theme and applies it to the document', () => {
    localStorage.setItem('media-ui-theme', 'tokyo-night');
    const service = TestBed.inject(ThemeService);
    TestBed.tick();

    expect(service.theme()).toBe('tokyo-night');
    expect(document.documentElement.dataset['theme']).toBe('tokyo-night');
  });

  it('falls back to GitHub Dark Pro on first run', () => {
    const service = TestBed.inject(ThemeService);
    TestBed.tick();

    expect(service.theme()).toBe('github-dark-pro');
    expect(document.documentElement.dataset['theme']).toBe('github-dark-pro');
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

  it('updates the theme-color meta tag when the theme changes', () => {
    const service = TestBed.inject(ThemeService);
    TestBed.tick();
    const meta = document.querySelector('meta[name="theme-color"]');

    expect(meta?.getAttribute('content')).toBe('#0d1117');

    service.setTheme('nocturne');
    TestBed.tick();
    expect(meta?.getAttribute('content')).toBe('#080d17');

    service.setTheme('tokyo-night');
    TestBed.tick();
    expect(meta?.getAttribute('content')).toBe('#16161e');

    service.setTheme('github-dark-pro');
    TestBed.tick();
    expect(meta?.getAttribute('content')).toBe('#0d1117');
  });
});

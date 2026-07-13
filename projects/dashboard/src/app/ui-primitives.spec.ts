import { TestBed } from '@angular/core/testing';
import { ThemeService } from 'media-ui';

describe('UI primitives', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.dataset['theme'] = '';
    TestBed.resetTestingModule();
  });

  it('applies and persists theme selections through ThemeService', () => {
    const service = TestBed.inject(ThemeService);
    service.setTheme('tokyo-night');
    TestBed.tick();

    expect(service.theme()).toBe('tokyo-night');
    expect(document.documentElement.dataset['theme']).toBe('tokyo-night');
    expect(localStorage.getItem('media-ui-theme')).toBe('tokyo-night');
  });
});

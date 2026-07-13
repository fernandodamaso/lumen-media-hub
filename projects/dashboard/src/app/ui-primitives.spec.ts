import { TestBed } from '@angular/core/testing';
import { MmButton } from 'media-ui';
import { ThemeService } from 'media-ui';

describe('UI primitives (ported from Storybook plays)', () => {
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

  it('lets the primary button receive keyboard focus', () => {
    const fixture = TestBed.createComponent(MmButton);
    fixture.componentRef.setInput('label', 'Focus me');
    fixture.detectChanges();
    const button = fixture.nativeElement.querySelector('button') as HTMLButtonElement;
    button.focus();
    expect(document.activeElement).toBe(button);
  });
});

import { TestBed } from '@angular/core/testing';
import { MmButton, MmThemePicker } from 'media-ui';

describe('UI primitives (ported from Storybook plays)', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.dataset['theme'] = '';
    TestBed.resetTestingModule();
  });

  it('applies and persists a selected theme through the picker control', () => {
    const fixture = TestBed.createComponent(MmThemePicker);
    fixture.detectChanges();

    const select = fixture.nativeElement.querySelector('select[aria-label="Choose theme"]') as HTMLSelectElement;
    expect(select).toBeTruthy();

    select.value = 'tokyo-night';
    select.dispatchEvent(new Event('change', { bubbles: true }));
    fixture.detectChanges();

    expect(select.value).toBe('tokyo-night');
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

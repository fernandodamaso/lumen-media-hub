import { TestBed } from '@angular/core/testing';
import { MmThemePicker } from './theme-picker';

describe('MmThemePicker', () => {
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
});

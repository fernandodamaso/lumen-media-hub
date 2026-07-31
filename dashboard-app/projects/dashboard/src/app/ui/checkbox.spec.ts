import { TestBed } from '@angular/core/testing';
import { fixtureHost } from '../../testing/fixture-host';
import { MmCheckbox } from './checkbox';

describe('MmCheckbox', () => {
  it('toggles checked on change', () => {
    const fixture = TestBed.createComponent(MmCheckbox);
    fixture.detectChanges();
    const input = fixtureHost(fixture).querySelector('input') as HTMLInputElement;
    input.checked = true;
    input.dispatchEvent(new Event('change'));
    expect(fixture.componentInstance.checked()).toBe(true);
  });
});

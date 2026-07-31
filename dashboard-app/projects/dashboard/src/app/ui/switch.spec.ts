import { TestBed } from '@angular/core/testing';
import { fixtureHost } from '../../testing/fixture-host';
import { MmSwitch } from './switch';

describe('MmSwitch', () => {
  it('toggles checked on change', () => {
    const fixture = TestBed.createComponent(MmSwitch);
    fixture.detectChanges();
    const input = fixtureHost(fixture).querySelector('input') as HTMLInputElement;
    input.checked = true;
    input.dispatchEvent(new Event('change'));
    expect(fixture.componentInstance.checked()).toBe(true);
  });
});

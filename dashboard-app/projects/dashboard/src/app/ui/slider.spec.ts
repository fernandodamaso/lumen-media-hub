import { TestBed } from '@angular/core/testing';
import { fixtureHost } from '../../testing/fixture-host';
import { MmSlider } from './slider';

describe('MmSlider', () => {
  it('updates value on input', () => {
    const fixture = TestBed.createComponent(MmSlider);
    fixture.detectChanges();
    const input = fixtureHost(fixture).querySelector('input') as HTMLInputElement;
    input.value = '75';
    input.dispatchEvent(new Event('input'));
    expect(fixture.componentInstance.value()).toBe(75);
  });
});

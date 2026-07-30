import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { fixtureHost } from '../../testing/fixture-host';
import { MmCheckbox } from './checkbox';

describe('MmCheckbox', () => {
  it('emits checkedChange on toggle', () => {
    const fixture = TestBed.createComponent(MmCheckbox);
    const onChange = vi.fn();
    fixture.componentInstance.checkedChange.subscribe(onChange);
    fixture.detectChanges();
    const input = fixtureHost(fixture).querySelector('input') as HTMLInputElement;
    input.checked = true;
    input.dispatchEvent(new Event('change'));
    expect(onChange).toHaveBeenCalledWith(true);
  });
});

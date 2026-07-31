import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { fixtureHost } from '../../testing/fixture-host';
import { MmRadio } from './radio';

describe('MmRadio', () => {
  it('emits the selected value on change', () => {
    const fixture = TestBed.createComponent(MmRadio);
    const onSelect = vi.fn();
    fixture.componentRef.setInput('name', 'quality');
    fixture.componentRef.setInput('value', 'a');
    fixture.componentInstance.valueSelect.subscribe(onSelect);
    fixture.detectChanges();
    const input = fixtureHost(fixture).querySelector('input') as HTMLInputElement;
    input.checked = true;
    input.dispatchEvent(new Event('change'));
    expect(onSelect).toHaveBeenCalledWith('a');
  });
});

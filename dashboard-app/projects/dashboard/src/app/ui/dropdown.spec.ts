import { TestBed } from '@angular/core/testing';
import { fixtureHost } from '../../testing/fixture-host';
import { MmDropdown } from './dropdown';

describe('MmDropdown', () => {
  it('opens on trigger click', () => {
    const fixture = TestBed.createComponent(MmDropdown);
    fixture.componentRef.setInput('groups', [{ items: [{ id: '1', label: 'One' }] }]);
    fixture.detectChanges();
    const trigger = fixtureHost(fixture).querySelector('button') as HTMLButtonElement;
    trigger.click();
    fixture.detectChanges();
    expect(fixture.componentInstance.open()).toBe(true);
  });
});

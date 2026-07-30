import { TestBed } from '@angular/core/testing';
import { fixtureHost } from '../../testing/fixture-host';
import { MmPopover } from './popover';

describe('MmPopover', () => {
  it('toggles open state', () => {
    const fixture = TestBed.createComponent(MmPopover);
    fixture.detectChanges();
    const trigger = fixtureHost(fixture).querySelector('button') as HTMLButtonElement;
    trigger.click();
    expect(fixture.componentInstance.open()).toBe(true);
  });
});

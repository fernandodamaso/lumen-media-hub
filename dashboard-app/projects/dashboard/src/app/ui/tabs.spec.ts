import { TestBed } from '@angular/core/testing';
import { fixtureHost } from '../../testing/fixture-host';
import { MmTabs } from './tabs';

describe('MmTabs', () => {
  it('activates tab on click', () => {
    const fixture = TestBed.createComponent(MmTabs);
    fixture.componentRef.setInput('tabs', [
      { id: 'a', label: 'A' },
      { id: 'b', label: 'B' },
    ]);
    fixture.componentRef.setInput('active', 'a');
    fixture.detectChanges();
    const buttons = fixtureHost(fixture).querySelectorAll('button');
    buttons[1].click();
    fixture.detectChanges();
    expect(fixture.componentInstance.active()).toBe('b');
  });

  it('sets aria-selected on active tab', () => {
    const fixture = TestBed.createComponent(MmTabs);
    fixture.componentRef.setInput('tabs', [
      { id: 'a', label: 'A' },
      { id: 'b', label: 'B' },
    ]);
    fixture.componentRef.setInput('active', 'a');
    fixture.detectChanges();
    const buttons = fixtureHost(fixture).querySelectorAll('button');
    expect(buttons[0].getAttribute('aria-selected')).toBe('true');
    expect(buttons[1].getAttribute('aria-selected')).toBe('false');
  });
});

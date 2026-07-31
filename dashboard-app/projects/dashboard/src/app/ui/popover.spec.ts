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

  it('keeps panel mounted while closed with aria-hidden/inert', () => {
    const fixture = TestBed.createComponent(MmPopover);
    fixture.detectChanges();
    const panel = fixtureHost(fixture).querySelector('[role="dialog"]') as HTMLElement;
    expect(panel).toBeTruthy();
    expect(panel.classList.contains('mm-popover__panel--open')).toBe(false);
    expect(panel.getAttribute('aria-hidden')).toBe('true');
    expect(panel.getAttribute('inert')).toBe('');
  });

  it('syncs aria-expanded on open', () => {
    const fixture = TestBed.createComponent(MmPopover);
    fixture.detectChanges();
    const trigger = fixtureHost(fixture).querySelector('button') as HTMLButtonElement;
    trigger.click();
    fixture.detectChanges();
    expect(trigger.getAttribute('aria-expanded')).toBe('true');
    expect(panelOpen(fixture)).toBe(true);
  });
});

function panelOpen(fixture: ReturnType<typeof TestBed.createComponent<MmPopover>>): boolean {
  const panel = fixtureHost(fixture).querySelector('[role="dialog"]') as HTMLElement;
  return panel.classList.contains('mm-popover__panel--open');
}

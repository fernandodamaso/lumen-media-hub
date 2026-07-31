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

  it('keeps menu mounted while closed with aria-hidden/inert', () => {
    const fixture = TestBed.createComponent(MmDropdown);
    fixture.componentRef.setInput('groups', [{ items: [{ id: '1', label: 'One' }] }]);
    fixture.detectChanges();
    const menu = fixtureHost(fixture).querySelector('[role="menu"]') as HTMLElement;
    expect(menu).toBeTruthy();
    expect(menu.classList.contains('mm-dropdown__menu--open')).toBe(false);
    expect(menu.getAttribute('aria-hidden')).toBe('true');
    expect(menu.getAttribute('inert')).toBe('');
  });

  it('syncs aria-expanded and moves focus into the menu on open', async () => {
    const fixture = TestBed.createComponent(MmDropdown);
    fixture.componentRef.setInput('groups', [{ items: [{ id: '1', label: 'One' }] }]);
    fixture.detectChanges();
    const trigger = fixtureHost(fixture).querySelector('button') as HTMLButtonElement;
    trigger.click();
    fixture.detectChanges();
    await fixture.whenStable();
    expect(trigger.getAttribute('aria-expanded')).toBe('true');
    expect(document.activeElement?.getAttribute('role')).toBe('menuitem');
  });
});

describe('MmDropdown icons', () => {
  it('renders an icon for items that declare one', () => {
    const fixture = TestBed.createComponent(MmDropdown);
    fixture.componentRef.setInput('groups', [
      { items: [{ id: 'scan', label: 'Scan disk', icon: 'scan' }, { id: 'plain', label: 'Plain' }] },
    ]);
    fixture.detectChanges();
    const items = fixtureHost(fixture).querySelectorAll('.mm-dropdown__item');
    expect(items[0].querySelector('svg')).toBeTruthy();
    expect(items[1].querySelector('svg')).toBeNull();
  });
});

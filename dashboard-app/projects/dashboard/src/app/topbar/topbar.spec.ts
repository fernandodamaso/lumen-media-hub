import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { fixtureHost } from '../../testing/fixture-host';
import { Topbar } from './topbar';

describe('Topbar', () => {
  it('renders the search pill with the platform shortcut label', () => {
    const fixture = TestBed.createComponent(Topbar);
    fixture.componentRef.setInput('shortcutLabel', '⌘K');
    fixture.detectChanges();

    const pill = fixtureHost(fixture).querySelector('[data-testid="topbar-search"]');
    expect(pill).toBeTruthy();
    expect(pill?.textContent).toContain('Search movies, shows, people');
    expect(pill?.querySelector('kbd')?.textContent).toContain('⌘K');
  });

  it('emits search when the pill is activated', () => {
    const fixture = TestBed.createComponent(Topbar);
    const onSearch = vi.fn();
    fixture.componentInstance.searchOpen.subscribe(onSearch);
    fixture.detectChanges();

    (fixtureHost(fixture).querySelector('[data-testid="topbar-search"]') as HTMLButtonElement).click();
    expect(onSearch).toHaveBeenCalledTimes(1);
  });

  it('emits addMedia from the gold Add media button', () => {
    const fixture = TestBed.createComponent(Topbar);
    const onAdd = vi.fn();
    fixture.componentInstance.addMedia.subscribe(onAdd);
    fixture.detectChanges();

    const button = fixtureHost(fixture).querySelector('[data-testid="topbar-add-media"] button') as HTMLButtonElement;
    expect(button.textContent).toContain('Add media');
    button.click();
    expect(onAdd).toHaveBeenCalledTimes(1);
  });
});

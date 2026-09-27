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
    expect(pill?.textContent).toContain('Search movies and shows');
    expect(pill?.textContent).not.toContain('people');
    expect(pill?.getAttribute('aria-label')).toBe('Search movies and shows');
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

  it('emits railToggle and reflects the rail state', () => {
    const fixture = TestBed.createComponent(Topbar);
    const onRailToggle = vi.fn();
    fixture.componentRef.setInput('railOpen', true);
    fixture.componentInstance.railToggle.subscribe(onRailToggle);
    fixture.detectChanges();

    let button = fixtureHost(fixture).querySelector('[data-testid="topbar-toggle-rail"] button') as HTMLButtonElement;
    expect(button.getAttribute('aria-label')).toBe('Hide activity rail');
    expect(button.getAttribute('aria-pressed')).toBeNull();
    expect(button.getAttribute('aria-expanded')).toBe('true');
    expect(button.getAttribute('aria-controls')).toBe('activity-rail');

    button.click();
    expect(onRailToggle).toHaveBeenCalledTimes(1);

    fixture.componentRef.setInput('railOpen', false);
    fixture.detectChanges();
    button = fixtureHost(fixture).querySelector('[data-testid="topbar-toggle-rail"] button') as HTMLButtonElement;
    expect(button.getAttribute('aria-label')).toBe('Show activity rail');
    expect(button.getAttribute('aria-expanded')).toBe('false');
  });
});

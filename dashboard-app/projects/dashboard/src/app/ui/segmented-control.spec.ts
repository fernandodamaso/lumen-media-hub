import { TestBed } from '@angular/core/testing';
import { fixtureHost } from '../../testing/fixture-host';
import { MmSegmentedControl } from './segmented-control';

describe('MmSegmentedControl', () => {
  it('renders radio semantics and moves the roving focus with Home/End', async () => {
    const fixture = TestBed.createComponent(MmSegmentedControl);
    fixture.componentRef.setInput('options', [
      { value: 'all', label: 'All' },
      { value: 'movies', label: 'Movies' },
      { value: 'series', label: 'Series' },
    ]);
    fixture.componentRef.setInput('value', 'movies');
    fixture.componentRef.setInput('label', 'Library filter');
    fixture.detectChanges();
    const root = fixtureHost(fixture);
    const buttons = [...root.querySelectorAll<HTMLButtonElement>('[role="radio"]')];
    expect(root.querySelector('[role="radiogroup"]')?.getAttribute('aria-label')).toBe('Library filter');
    expect(buttons[1].getAttribute('aria-checked')).toBe('true');
    expect(buttons[0].tabIndex).toBe(-1);
    buttons[1].focus();
    buttons[1].dispatchEvent(new KeyboardEvent('keydown', { key: 'End', bubbles: true }));
    await fixture.whenStable();
    expect(fixture.componentInstance.value()).toBe('series');
    expect(document.activeElement).toBe(buttons[2]);
  });
});

import { TestBed } from '@angular/core/testing';
import { fixtureHost } from '../../testing/fixture-host';
import { MmAccordion } from './accordion';

describe('MmAccordion', () => {
  it('allows multiple open sections by default', () => {
    const fixture = TestBed.createComponent(MmAccordion);
    fixture.componentRef.setInput('items', [
      { id: 'a', title: 'A', content: 'One' },
      { id: 'b', title: 'B', content: 'Two' },
    ]);
    fixture.detectChanges();
    const root = fixtureHost(fixture);
    const buttons = root.querySelectorAll('button');
    buttons[0].click();
    buttons[1].click();
    fixture.detectChanges();
    expect(root.querySelectorAll('.mm-accordion__panel')).toHaveLength(2);
    expect(root.querySelectorAll('.mm-accordion__panel--open')).toHaveLength(2);
  });

  it('keeps panels mounted while closed with aria-hidden/inert', () => {
    const fixture = TestBed.createComponent(MmAccordion);
    fixture.componentRef.setInput('items', [{ id: 'a', title: 'A', content: 'One' }]);
    fixture.detectChanges();
    const root = fixtureHost(fixture);
    const panel = root.querySelector('.mm-accordion__panel') as HTMLElement;
    expect(panel).toBeTruthy();
    expect(panel.classList.contains('mm-accordion__panel--open')).toBe(false);
    expect(panel.getAttribute('aria-hidden')).toBe('true');
    expect(panel.getAttribute('inert')).toBe('');
  });

  it('uses grid-template-rows for height animation', () => {
    const fixture = TestBed.createComponent(MmAccordion);
    fixture.componentRef.setInput('items', [{ id: 'a', title: 'A', content: 'One' }]);
    fixture.detectChanges();
    const panel = fixtureHost(fixture).querySelector('.mm-accordion__panel') as HTMLElement;
    expect(getComputedStyle(panel).gridTemplateRows).toBe('0fr');
  });
});

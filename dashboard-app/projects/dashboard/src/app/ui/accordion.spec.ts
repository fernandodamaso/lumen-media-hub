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
  });
});

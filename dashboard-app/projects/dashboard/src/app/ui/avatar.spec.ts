import { TestBed } from '@angular/core/testing';
import { fixtureHost } from '../../testing/fixture-host';
import { MmAvatar } from './avatar';

describe('MmAvatar', () => {
  it('renders initials', () => {
    const fixture = TestBed.createComponent(MmAvatar);
    fixture.componentRef.setInput('initials', 'AB');
    fixture.detectChanges();
    expect(fixtureHost(fixture).textContent).toContain('AB');
  });
});

import { TestBed } from '@angular/core/testing';
import { fixtureHost } from '../../testing/fixture-host';
import { MmSeparator } from './separator';

describe('MmSeparator', () => {
  it('renders horizontal by default', () => {
    const fixture = TestBed.createComponent(MmSeparator);
    fixture.detectChanges();
    expect(fixtureHost(fixture).querySelector('.mm-separator--vertical')).toBeNull();
  });
});

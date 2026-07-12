import { ComponentFixture, TestBed } from '@angular/core/testing';

import { MediaUi } from './media-ui';

describe('MediaUi', () => {
  let component: MediaUi;
  let fixture: ComponentFixture<MediaUi>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [MediaUi],
    }).compileComponents();

    fixture = TestBed.createComponent(MediaUi);
    component = fixture.componentInstance;
    await fixture.whenStable();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});

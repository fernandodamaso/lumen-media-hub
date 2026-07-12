import { ComponentFixture, TestBed } from '@angular/core/testing';
import { DownloadsBoard } from './downloads-board';
import { DownloadsFacade } from './downloads.facade';
import { MEDIA_STACK_API } from './media-stack-api';
import { MockMediaStackApi } from './mock-media-stack-api';

describe('DownloadsBoard', () => {
  let fixture: ComponentFixture<DownloadsBoard>;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [DownloadsBoard],
      providers: [DownloadsFacade, { provide: MEDIA_STACK_API, useClass: MockMediaStackApi }],
    });
    fixture = TestBed.createComponent(DownloadsBoard);
  });

  it('renders the populated mock queue with accessible progress and controls', async () => {
    await TestBed.inject(DownloadsFacade).refresh();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Downloads');
    expect(fixture.nativeElement.textContent).toContain('Afterlight');
    expect(fixture.nativeElement.querySelectorAll('[role="progressbar"]')).toHaveLength(3);
    expect(fixture.nativeElement.querySelector('[aria-label="Download controls"]')).toBeTruthy();
  });

});

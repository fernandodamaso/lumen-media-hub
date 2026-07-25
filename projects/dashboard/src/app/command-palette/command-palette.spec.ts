import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { signal } from '@angular/core';
import { vi } from 'vitest';
import { fixtureHost } from '../../testing/fixture-host';
import { AutomationFacade } from '../automation/automation.facade';
import { ServiceHealthFacade } from '../automation/service-health.facade';
import { CalendarFacade } from '../calendar/calendar.facade';
import { DownloadsFacade } from '../downloads/downloads.facade';
import { LibraryItem } from '../library/library.models';
import { LibraryItemsFacade } from '../library/library-items.facade';
import { LibraryStatsFacade } from '../library/library-stats.facade';
import { StorageFacade } from '../storage/storage.facade';
import { CommandPalette } from './command-palette';

describe('CommandPalette', () => {
  let fixture: ComponentFixture<CommandPalette>;
  let router: Router;
  let downloads: { runAction: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    downloads = { runAction: vi.fn(() => Promise.resolve()) };
    TestBed.configureTestingModule({
      imports: [CommandPalette],
      providers: [
        provideRouter([{ path: '**', children: [] }]),
        {
          provide: LibraryItemsFacade,
          useValue: {
            items: signal<LibraryItem[]>([
              {
                id: 'm1',
                title: 'Moonrise',
                kind: 'movie',
                meta: '2024 · Movie',
                art: 'linear-gradient(#000, #111)',
                overview: '',
                href: null,
                artworkState: 'ok',
                playable: true,
              },
            ]),
            refresh: vi.fn(),
          },
        },
        { provide: ServiceHealthFacade, useValue: { refresh: vi.fn() } },
        { provide: LibraryStatsFacade, useValue: { refresh: vi.fn() } },
        { provide: DownloadsFacade, useValue: downloads },
        { provide: StorageFacade, useValue: { refresh: vi.fn() } },
        { provide: CalendarFacade, useValue: { refresh: vi.fn() } },
        { provide: AutomationFacade, useValue: { refresh: vi.fn() } },
      ],
    });
    fixture = TestBed.createComponent(CommandPalette);
    router = TestBed.inject(Router);
    vi.spyOn(router, 'navigateByUrl').mockResolvedValue(true);
  });

  it('filters results and navigates on selection', async () => {
    fixture.componentRef.setInput('open', true);
    fixture.detectChanges();

    const root = fixtureHost(fixture);
    expect(root.querySelector('[data-testid="command-palette"]')).toBeTruthy();
    expect(root.textContent).toContain('Dashboard');
    expect(root.textContent).toContain('Moonrise');

    const input = root.querySelector('input') as HTMLInputElement;
    input.value = 'pause';
    input.dispatchEvent(new Event('input'));
    fixture.detectChanges();

    expect(root.textContent).toContain('Pause all');
    expect(root.textContent).not.toContain('Moonrise');

    const pause = [...root.querySelectorAll('.palette__item')].find((node) =>
      node.textContent.includes('Pause all'),
    ) as HTMLButtonElement;
    pause.click();
    await fixture.whenStable();
    expect(downloads.runAction).toHaveBeenCalledWith('pause');
  });

  it('resets query when opened via the open input', () => {
    fixture.componentRef.setInput('open', true);
    fixture.detectChanges();
    fixture.componentInstance.query.set('pause');
    fixture.detectChanges();

    fixture.componentRef.setInput('open', false);
    fixture.detectChanges();
    fixture.componentRef.setInput('open', true);
    fixture.detectChanges();

    expect(fixture.componentInstance.query()).toBe('');
    expect(fixture.componentInstance.activeIndex()).toBe(0);
  });

  it('opens and closes with keyboard shortcuts', () => {
    const openChange = vi.fn();
    fixture.componentInstance.openChange.subscribe(openChange);
    fixture.componentRef.setInput('open', false);
    fixture.detectChanges();

    fixture.componentInstance.onDocumentKeydown(
      new KeyboardEvent('keydown', { key: 'k', ctrlKey: true }),
    );
    expect(openChange).toHaveBeenCalledWith(true);

    fixture.componentRef.setInput('open', true);
    fixture.detectChanges();
    fixture.componentInstance.onDocumentKeydown(new KeyboardEvent('keydown', { key: 'Escape' }));
    expect(openChange).toHaveBeenCalledWith(false);
  });
});

import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { MmToastService } from './toast.service';

describe('MmToastService', () => {
  it('queues and dismisses messages', () => {
    vi.useFakeTimers();
    const service = TestBed.inject(MmToastService);
    service.show('Saved');
    expect(service.messages()).toHaveLength(1);
    vi.advanceTimersByTime(5000);
    expect(service.messages()).toHaveLength(0);
    vi.useRealTimers();
  });

  it('marks toast as hidden before removal', () => {
    vi.useFakeTimers();
    const service = TestBed.inject(MmToastService);
    service.show('Saved');
    const id = service.messages()[0].id;
    service.dismiss(id);
    expect(service.messages()).toHaveLength(1);
    expect(service.messages()[0].hidden).toBe(true);
    vi.advanceTimersByTime(400);
    expect(service.messages()).toHaveLength(0);
    vi.useRealTimers();
  });
});

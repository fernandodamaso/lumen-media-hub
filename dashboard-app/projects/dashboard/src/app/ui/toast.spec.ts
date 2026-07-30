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
});

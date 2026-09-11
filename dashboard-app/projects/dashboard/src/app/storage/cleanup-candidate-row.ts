import { ChangeDetectionStrategy, Component, computed, input, output, signal } from '@angular/core';

import { MmButton } from '../ui/button';
import { MmStatus } from '../ui/status';
import { CleanupCandidate } from './cleanup.models';
import { formatCandidateMeta, formatCandidateReason, formatCleanupBytes, formatCleanupReason } from './cleanup-format';

@Component({
  selector: 'app-cleanup-candidate-row',
  imports: [MmButton, MmStatus],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './cleanup-candidate-row.html',
  styleUrl: './cleanup-candidate-row.scss',
})
export class CleanupCandidateRow {
  readonly candidate = input.required<CleanupCandidate>();
  readonly generatedAt = input.required<string>();
  readonly pinned = input(false);
  readonly keep = output<string>();
  readonly detailsOpen = signal(false);

  readonly sizeLabel = computed(() => formatCleanupBytes(this.candidate().sizeBytes));
  readonly meta = computed(() => formatCandidateMeta(this.candidate(), this.generatedAt()));
  readonly reason = computed(() => formatCandidateReason(this.candidate()));

  toggleDetails(): void {
    this.detailsOpen.update((open) => !open);
  }

  keepItem(): void {
    if (!this.pinned()) this.keep.emit(this.candidate().id);
  }

  reasonDetail(): string[] {
    return this.candidate().reasons.map(formatCleanupReason);
  }
}

import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { LucideActivity, LucideBookmark, LucideDownload, LucideHardDrive } from '@lucide/angular';

import { MmButton } from '../ui/button';
import { MmInput } from '../ui/input';
import { MmSegmentedControl, MmSegmentedOption } from '../ui/segmented-control';
import { MmStatus } from '../ui/status';
import { MmSwitch } from '../ui/switch';
import { MmTabItem, MmTabs } from '../ui/tabs';
import { CleanupCandidateRow } from './cleanup-candidate-row';
import { formatCleanupBytes } from './cleanup-format';
import { CleanupCandidate, GIB } from './cleanup.models';
import { CleanupPreviewFacade } from './cleanup-preview.facade';

export type CleanupFilter = 'suggested' | 'all' | 'kept' | 'review';

@Component({
  selector: 'app-storage-guardian-page',
  imports: [
    CleanupCandidateRow,
    LucideActivity,
    LucideBookmark,
    LucideDownload,
    LucideHardDrive,
    MmButton,
    MmInput,
    MmSegmentedControl,
    MmStatus,
    MmSwitch,
    MmTabs,
  ],
  providers: [CleanupPreviewFacade],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './storage-guardian.page.html',
  styleUrl: './storage-guardian.page.scss',
})
export class StorageGuardianPage {
  readonly facade = inject(CleanupPreviewFacade);
  readonly filter = signal<CleanupFilter>('suggested');
  readonly desktopFilters: MmSegmentedOption<CleanupFilter>[] = [
    { value: 'suggested', label: 'Suggested' },
    { value: 'all', label: 'All matches' },
    { value: 'kept', label: 'Kept' },
    { value: 'review', label: 'Needs review' },
  ];
  readonly mobileTabs: MmTabItem[] = [
    { id: 'suggested', label: 'Suggested' },
    { id: 'all', label: 'All matches' },
  ];

  readonly candidates = computed(() => {
    const preview = this.facade.preview();
    if (!preview) return [];
    switch (this.filter()) {
      case 'suggested': return preview.candidates.filter((candidate) => candidate.recommended && !this.facade.isPinned(candidate.id));
      case 'kept': return preview.candidates.filter((candidate) => this.facade.isPinned(candidate.id));
      case 'review': return [];
      default: return preview.candidates;
    }
  });

  readonly targetGib = computed(() => Math.round(this.facade.policy().targetFreeBytes / GIB));
  readonly minimumGib = computed(() => Math.round(this.facade.policy().rules.largeWatchedFiles.minimumBytes / GIB));
  readonly stateLabel = computed(() => {
    const preview = this.facade.preview();
    if (!preview) return this.facade.phase() === 'error' ? 'Preview unavailable' : 'Ready to simulate';
    if (preview.status === 'degraded') return 'Degraded preview';
    if (preview.storage.requiredReclaimBytes === 0) return 'Target met';
    if (preview.storage.remainingShortfallBytes > 0) return 'Capacity shortfall';
    return 'Capacity ready';
  });
  readonly stateTone = computed<'success' | 'warning' | 'gold'>(() => {
    const preview = this.facade.preview();
    if (!preview) return 'gold';
    if (preview.status === 'degraded' || preview.storage.remainingShortfallBytes > 0) return 'warning';
    return 'success';
  });

  setFilter(value: string): void {
    if (value === 'suggested' || value === 'all' || value === 'kept' || value === 'review') this.filter.set(value);
  }

  metricValue(kind: 'free' | 'target' | 'recommended' | 'projected'): string {
    const preview = this.facade.preview();
    if (kind === 'target') return formatCleanupBytes(this.facade.policy().targetFreeBytes);
    if (!preview) return '—';
    if (kind === 'free') return formatCleanupBytes(preview.storage.freeBytes);
    if (kind === 'recommended') return formatCleanupBytes(preview.storage.recommendedBytes);
    return formatCleanupBytes(preview.storage.projectedFreeBytes);
  }

  metricSupport(kind: 'free' | 'target' | 'recommended' | 'projected'): string {
    const preview = this.facade.preview();
    if (kind === 'target') return 'Configured minimum';
    if (!preview) return 'Run preview to calculate';
    if (kind === 'free') {
      return preview.storage.requiredReclaimBytes
        ? `${formatCleanupBytes(preview.storage.requiredReclaimBytes)} below target`
        : 'Target already met';
    }
    if (kind === 'recommended') return `${preview.summary.recommendedFiles} safe candidates`;
    return preview.storage.remainingShortfallBytes
      ? `${formatCleanupBytes(preview.storage.remainingShortfallBytes)} short`
      : 'Target restored';
  }

  resultsSummary(): string {
    const preview = this.facade.preview();
    if (!preview) return 'No inventory is scanned until you run the preview.';
    return `${preview.summary.recommendedFiles} files selected · ${formatCleanupBytes(preview.storage.recommendedBytes)} · projected free space ${formatCleanupBytes(preview.storage.projectedFreeBytes)}.`;
  }

  rulesSummary(): string {
    const policy = this.facade.policy();
    return `Movies ${policy.rules.watchedMovies.retentionDays} days · Episodes ${policy.rules.watchedEpisodes.retentionDays} days · Keep ${policy.rules.watchedEpisodes.keepLatestPerSeries} · Target ${this.targetGib()} GB`;
  }

  keepCandidate(candidate: CleanupCandidate): void {
    this.facade.keepCandidate(candidate.id);
  }
}

import {
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { LucideChevronRight } from '@lucide/angular';
import {
  MmButton,
  MmDialog,
  MmDialogTone,
  MmProgress,
  MmSkeleton,
  MmStateCard,
  MmStatus,
} from '@app/ui';
import {
  AutomationProblem,
  AutomationProblemItem,
  AutomationProblemSeverity,
  AutomationService,
  AutomationServiceStatus,
  compareAutomationServices,
} from '../../automation/automation.models';
import {
  AUTOMATION_PROBLEM_SEVERITY_VIEW,
  AUTOMATION_SERVICE_STATUS_VIEW,
  formatShortDate,
} from '../../automation/automation-format';
import { resolveServiceHref } from '../../automation/service-catalog';
import { ServiceHealthFacade } from '../../automation/service-health.facade';
import { SERVICE_LINK_BASES } from '../../media-stack/media-stack-api.providers';
import { StorageFacade } from '../../storage/storage.facade';
import { formatStorageBytes, STORAGE_VOLUME_TONE } from '../../storage/storage-format';
import { StorageVolume } from '../../storage/storage.models';

const PROBLEM_SEVERITY_RANK: Record<AutomationProblemSeverity, number> = {
  actionable: 0,
  warning: 1,
  info: 2,
};

const PROBLEM_SEVERITY_ORDER: AutomationProblemSeverity[] = ['actionable', 'warning', 'info'];

const EPISODE_CODE_RE = /\sS(\d+)E(\d+)$/;
// ponytail: stats parsed from backend display string; if homepage-actions adds structured fields, map those instead
const ARR_DETAIL_RE = /^(\d+)\s+missing\s+·\s+(\d+)\s+(?:shows|movies)\s+·\s+(\d+)\s+queued$/;
const POSTER_TONES = ['ph-1', 'ph-2', 'ph-3'];

interface ArrStat { value: number; label: string; }

interface DialogItemRow { key: string; title: string; season: number | null; episode: number | null; when: string; href: string | null; }
interface DialogItemGroup { key: string; label: string; href: string | null; posterUrl: string | null; initials: string; toneClass: string; rows: DialogItemRow[]; }
interface DialogProblemView { id: string; summary: string; moreCount: number; groups: DialogItemGroup[]; }

@Component({
  selector: 'mm-automation-card',
  imports: [
    MmButton,
    MmDialog,
    MmProgress,
    MmSkeleton,
    MmStateCard,
    MmStatus,
    RouterLink,
    LucideChevronRight,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './automation-card.html',
  styleUrl: './automation-card.scss',
})
export class AutomationCard {
  readonly health = inject(ServiceHealthFacade);
  readonly storage = inject(StorageFacade);
  private readonly linkBases = inject(SERVICE_LINK_BASES);
  private readonly cdr = inject(ChangeDetectorRef);
  private readonly serviceDialog = viewChild.required<MmDialog>('serviceDialog');

  readonly skeletonRows = [0, 1, 2, 3];
  readonly formatBytes = formatStorageBytes;

  readonly selectedService = signal<AutomationService | null>(null);

  readonly flaggedServices = computed(() =>
    this.health
      .services()
      .filter((service) => service.status !== 'healthy')
      .sort(compareAutomationServices),
  );

  readonly healthyServices = computed(() =>
    this.health.services().filter((service) => service.status === 'healthy'),
  );

  readonly selectedProblems = computed(() => {
    const serviceId = this.selectedService()?.id;
    if (!serviceId) return [];
    return this.health
      .problems()
      .filter((problem) => problem.serviceId === serviceId)
      .sort((left, right) => PROBLEM_SEVERITY_RANK[left.severity] - PROBLEM_SEVERITY_RANK[right.severity]);
  });

  readonly selectedProblemGroups = computed(() => {
    const serviceId = this.selectedService()?.id ?? null;
    let problemIdx = 0;
    return PROBLEM_SEVERITY_ORDER.map((severity) => ({
      severity,
      label: AUTOMATION_PROBLEM_SEVERITY_VIEW[severity].label,
      problems: this.selectedProblems()
        .filter((problem) => problem.severity === severity)
        .map((problem) => toDialogProblemView(problem, serviceId, problemIdx++)),
    })).filter((group) => group.problems.length > 0);
  });

  readonly libraryVolume = computed(() => {
    const volumes = this.storage.volumes();
    const library = volumes.find((volume) => volume.kind === 'library');
    if (library) return library;
    return volumes.length > 0 ? volumes[0] : null;
  });

  constructor() {
    this.storage.startPolling();
  }

  statusLabel(status: AutomationServiceStatus): string {
    return AUTOMATION_SERVICE_STATUS_VIEW[status].label;
  }

  readonly arrStats = computed<ArrStat[] | null>(() => {
    const service = this.selectedService();
    if (!service || !isArrId(service.id)) return null;
    return parseArrDetail(service.detail, service.id);
  });

  readonly selectedShowCards = computed<DialogItemGroup[]>(() => {
    const service = this.selectedService();
    if (!service || !isArrId(service.id)) return [];
    const cards: DialogItemGroup[] = [];
    for (const group of this.selectedProblemGroups()) {
      for (const problem of group.problems) {
        cards.push(...problem.groups);
      }
    }
    return cards;
  });

  readonly arrMoreCount = computed(() => {
    const service = this.selectedService();
    if (!service || !isArrId(service.id)) return 0;
    return this.selectedProblems().reduce(
      (sum, p) => sum + Math.max(0, (p.itemCount ?? 0) - (p.items?.length ?? 0)),
      0,
    );
  });

  onPosterError(event: Event): void {
    (event.target as HTMLImageElement).style.display = 'none';
  }

  isArrService(id: string): boolean {
    return isArrId(id);
  }

  arrSectionHeading(id: string): string {
    const problems = this.selectedProblems();
    if (id === 'sonarr') {
      if (problems.some((problem) => problem.id === 'sonarr-missing')) return 'Missing episodes';
      if (problems.some((problem) => problem.id === 'sonarr-queue')) return 'Queue warnings';
      const stats = this.arrStats();
      if ((stats?.[0]?.value ?? 0) > 0) return 'Missing episodes';
      if ((stats?.[2]?.value ?? 0) > 0) return 'Queue warnings';
      return '';
    }
    if (id === 'radarr') {
      if (problems.some((problem) => problem.id === 'radarr-missing')) return 'Missing movies';
      if (problems.some((problem) => problem.id === 'radarr-queue')) return 'Queue warnings';
      const stats = this.arrStats();
      if ((stats?.[0]?.value ?? 0) > 0) return 'Missing movies';
      if ((stats?.[2]?.value ?? 0) > 0) return 'Queue warnings';
      return '';
    }
    return '';
  }

  cardSubtitle(serviceId: string, card: DialogItemGroup): string {
    if (serviceId === 'radarr') return 'Missing movie';
    const row = card.rows[0];
    if (row.season != null && row.episode != null) {
      return `Season ${row.season} · Episode ${row.episode}`;
    }
    return '';
  }

  dialogTone(status: AutomationServiceStatus | undefined): MmDialogTone {
    if (status === 'down') return 'danger';
    if (status === 'degraded') return 'warning';
    return 'default';
  }

  serviceHref(id: string): string | null {
    return resolveServiceHref(id, this.linkBases);
  }

  openService(service: AutomationService): void {
    this.selectedService.set(service);
    // Paint title/body before showModal so the first announcement is not stale.
    this.cdr.detectChanges();
    this.serviceDialog().open();
  }

  onDialogClosed(): void {
    this.selectedService.set(null);
  }

  barTone(volume: StorageVolume) {
    return STORAGE_VOLUME_TONE[volume.kind];
  }

  percent(volume: StorageVolume): number {
    if (!volume.totalBytes) return 0;
    return Math.min(100, Math.round((volume.usedBytes / volume.totalBytes) * 100));
  }

  retryHealth(): void {
    void this.health.refresh();
  }

  retryStorage(): void {
    void this.storage.refresh({ initial: true });
  }
}

function toDialogProblemView(problem: AutomationProblem, serviceId: string | null = null, problemIdx: number = 0): DialogProblemView {
  const items = problem.items ?? [];
  return {
    id: problem.id,
    summary: problem.summary,
    moreCount: problem.itemCount && problem.itemCount > items.length ? problem.itemCount - items.length : 0,
    groups: groupDialogItems(items, serviceId, `${problemIdx}`),
  };
}

function pickTone(key: string): string {
  let hash = 0;
  for (let i = 0; i < key.length; i++) hash = ((hash << 5) - hash) + key.charCodeAt(i);
  return POSTER_TONES[Math.abs(hash) % POSTER_TONES.length];
}

function groupDialogItems(items: AutomationProblemItem[], serviceId: string | null = null, problemId: string = ''): DialogItemGroup[] {
  const groups = new Map<string, DialogItemGroup>();
  let idx = 0;
  for (const item of items) {
    idx++;
    const match = serviceId === 'sonarr' ? EPISODE_CODE_RE.exec(item.title) : null;
    const href = item.href;
    if (match) {
      const label = item.title.slice(0, match.index);
      const key = `${problemId}::${label}`;
      let group = groups.get(key);
      if (!group) {
        group = { key, label, href, posterUrl: item.posterUrl, initials: (label.charAt(0) || '?').toUpperCase(), toneClass: pickTone(key), rows: [] };
        groups.set(key, group);
      } else if (item.posterUrl && !group.posterUrl) {
        group.posterUrl = item.posterUrl;
      }
      const season = parseInt(match[1], 10);
      const episode = parseInt(match[2], 10);
      const rowKey = `${key}-${idx}-${item.title}-${item.when}`;
      group.rows.push({ key: rowKey, title: item.title, season, episode, when: formatShortDate(item.when), href });
    } else {
      const label = item.title;
      const key = `${problemId}::${idx}-${href ?? label}`;
      const rowKey = `${key}-row`;
      const group: DialogItemGroup = { key, label, href, posterUrl: item.posterUrl, initials: (label.charAt(0) || '?').toUpperCase(), toneClass: pickTone(key), rows: [] };
      group.rows.push({ key: rowKey, title: item.title, season: null, episode: null, when: formatShortDate(item.when), href });
      groups.set(key, group);
    }
  }
  return [...groups.values()];
}

function parseArrDetail(detail: string, serviceId: string): ArrStat[] | null {
  const match = ARR_DETAIL_RE.exec(detail);
  if (!match) return null;
  const label = serviceId === 'sonarr' ? 'Shows' : 'Movies';
  return [
    { value: parseInt(match[1], 10), label: 'Missing' },
    { value: parseInt(match[2], 10), label },
    { value: parseInt(match[3], 10), label: 'Queued' },
  ];
}

function isArrId(id: string): boolean {
  return id === 'sonarr' || id === 'radarr';
}

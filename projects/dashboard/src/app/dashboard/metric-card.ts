import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { LucideActivity, LucideChevronRight, LucideDownload, LucideFolder, LucideHardDrive } from '@lucide/angular';
import { MmProgress } from '@app/ui';

type MetricIcon = 'folder' | 'download' | 'activity' | 'hard-drive';
export type MetricTone = 'premiere' | 'info' | 'success' | 'warning';

@Component({
  selector: 'mm-metric-card',
  imports: [MmProgress, LucideFolder, LucideDownload, LucideActivity, LucideHardDrive, LucideChevronRight],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './metric-card.html',
  styleUrl: './metric-card.scss',
})
export class MetricCard {
  readonly iconName = input<MetricIcon>('folder');
  readonly tone = input<MetricTone>('premiere');
  readonly label = input<string>('Label');
  readonly value = input<string | number>('—');
  readonly meta = input<string | null>(null);
  readonly progress = input<number | null>(null);
  readonly href = input<string | null>(null);
  readonly external = input<boolean>(false);
}

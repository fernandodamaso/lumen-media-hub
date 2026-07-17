import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { LucideActivity, LucideChevronRight, LucideDownload, LucideFolder, LucideHardDrive } from '@lucide/angular';

type MetricIcon = 'folder' | 'download' | 'activity' | 'hard-drive';

@Component({
  selector: 'mm-metric-card',
  imports: [LucideFolder, LucideDownload, LucideActivity, LucideHardDrive, LucideChevronRight],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './metric-card.html',
  styleUrl: './metric-card.scss',
})
export class MetricCard {
  readonly iconName = input<MetricIcon>('folder');
  readonly iconBg = input<string>('var(--mm-component-muted-bg)');
  readonly iconColor = input<string>('var(--mm-component-text-primary)');
  readonly label = input<string>('Label');
  readonly value = input<string | number>('—');
  readonly meta = input<string | null>(null);
  readonly progress = input<number | null>(null);
  readonly href = input<string | null>(null);
  readonly external = input<boolean>(false);
}

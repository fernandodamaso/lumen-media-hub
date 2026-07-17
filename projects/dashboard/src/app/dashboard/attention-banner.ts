import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { LucideAlertTriangle, LucideChevronRight } from '@lucide/angular';

@Component({
  selector: 'mm-attention-banner',
  imports: [RouterLink, LucideAlertTriangle, LucideChevronRight],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './attention-banner.html',
  styleUrl: './attention-banner.scss',
})
export class AttentionBanner {
  readonly headline = input.required<string>();
  readonly message = input.required<string>();
}

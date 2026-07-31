import { ChangeDetectionStrategy, Component, input, signal } from '@angular/core';
import { LucideFilm, LucideTv, LucideUser } from '@lucide/angular';

export type MmAvatarTone = 'default' | 'gold' | 'green' | 'violet';
export type MmAvatarSize = 'sm' | 'md' | 'lg';
export type MmAvatarIcon = 'user' | 'film' | 'tv';

@Component({
  selector: 'mm-avatar',
  imports: [LucideFilm, LucideTv, LucideUser],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span
    class="mm-avatar"
    [class]="'mm-avatar mm-avatar--' + size() + ' mm-avatar--' + tone()"
    [attr.aria-label]="label()"
    role="img"
  >@if (src() && !imgFailed()) {
    <img class="mm-avatar__img" [src]="src()" [alt]="label()" (error)="imgFailed.set(true)" />
  } @else if (icon() === 'user') {
    <svg lucideUser [size]="iconSize()" aria-hidden="true"></svg>
  } @else if (icon() === 'film') {
    <svg lucideFilm [size]="iconSize()" aria-hidden="true"></svg>
  } @else if (icon() === 'tv') {
    <svg lucideTv [size]="iconSize()" aria-hidden="true"></svg>
  } @else {
    {{ initials() }}
  }</span>`,
  styleUrl: './avatar.scss',
})
export class MmAvatar {
  readonly label = input('User');
  readonly initials = input('U');
  readonly tone = input<MmAvatarTone>('default');
  readonly size = input<MmAvatarSize>('md');
  /** Image URL; falls back to icon/initials if it fails to load. */
  readonly src = input<string | null>(null);
  /** Icon variant, used when no src is set (or the image failed). */
  readonly icon = input<MmAvatarIcon | ''>('');
  protected readonly imgFailed = signal(false);

  iconSize(): number {
    const sizes: Record<MmAvatarSize, number> = { sm: 13, md: 17, lg: 22 };
    return sizes[this.size()];
  }
}

@Component({
  selector: 'mm-avatar-stack',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<div class="mm-avatar-stack"><ng-content /></div>`,
  styleUrl: './avatar.scss',
})
export class MmAvatarStack {}

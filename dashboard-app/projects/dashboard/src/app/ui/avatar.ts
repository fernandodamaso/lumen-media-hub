import { ChangeDetectionStrategy, Component, input } from '@angular/core';

export type MmAvatarTone = 'default' | 'gold' | 'green' | 'violet';
export type MmAvatarSize = 'sm' | 'md' | 'lg';

@Component({
  selector: 'mm-avatar',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<span
    class="mm-avatar"
    [class]="'mm-avatar mm-avatar--' + size() + ' mm-avatar--' + tone()"
    [attr.aria-label]="label()"
    role="img"
  >{{ initials() }}</span>`,
  styleUrl: './avatar.scss',
})
export class MmAvatar {
  readonly label = input('User');
  readonly initials = input('U');
  readonly tone = input<MmAvatarTone>('default');
  readonly size = input<MmAvatarSize>('md');
}

@Component({
  selector: 'mm-avatar-stack',
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<div class="mm-avatar-stack"><ng-content /></div>`,
  styleUrl: './avatar.scss',
})
export class MmAvatarStack {}

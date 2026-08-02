export type MmButtonVariant =
  | 'primary'
  | 'quiet'
  | 'success'
  | 'warning'
  | 'danger'
  | 'gold'
  | 'ghost'
  | 'chip';

export type MmButtonSize = 'sm' | 'md' | 'lg';

export type MmButtonIconName = 'pause' | 'play' | 'plus' | 'refresh' | 'external-link' | 'info' | '';

export function mmButtonClasses(options: {
  variant: MmButtonVariant;
  size: MmButtonSize;
  solid: boolean;
  liftOnHover: boolean;
}): string {
  const { variant, size, solid, liftOnHover } = options;
  return `mm-button mm-button--${variant} mm-button--${size}${solid ? ' solid' : ''}${liftOnHover ? '' : ' mm-button--flat-hover'}`;
}

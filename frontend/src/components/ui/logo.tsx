/**
 * The mark: a provenance rail with three code lines beside it, the middle one
 * stopping short and ending in the corroboration teal.
 *
 * It is the review surface in miniature, which is the point - the rail and that
 * one teal dot are the two things this product actually asserts, so the logo
 * says them rather than decorating around them.
 *
 * The bone-white geometry is drawn in `currentColor` so the mark takes the
 * colour of whatever it sits in - header, heading, a muted footer. Only the dot
 * is pinned, to `--verified`, because that hue is the meaning and must not
 * drift with context.
 */

import { cn } from '@/lib/utils';

interface LogoProps {
  /** Rendered edge length in px. The header runs 20, headings 22. */
  size?: number;
  className?: string;
}

export function Logo({ size = 20, className }: LogoProps) {
  return (
    <svg
      aria-hidden
      focusable="false"
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      className={cn('shrink-0', className)}
    >
      <rect x="4" y="5" width="3" height="22" rx="1.5" fill="currentColor" />
      <rect x="11" y="6" width="17" height="3" rx="1.5" fill="currentColor" />
      <rect x="11" y="14.5" width="9" height="3" rx="1.5" fill="currentColor" />
      <circle cx="25" cy="16" r="2.75" fill="var(--verified)" />
      <rect x="11" y="23" width="13" height="3" rx="1.5" fill="currentColor" />
    </svg>
  );
}

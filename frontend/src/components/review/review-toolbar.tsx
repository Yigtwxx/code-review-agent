'use client';

import { Search } from 'lucide-react';

import { Button } from '@/components/ui/primitives';
import { SEVERITY_FILL, SEVERITY_LABEL, SEVERITY_ORDER } from '@/lib/display';
import type { Severity } from '@/lib/types';
import { cn } from '@/lib/utils';

interface ReviewToolbarProps {
  fileCount: number;
  /** Findings per severity across every file, before filtering. */
  counts: Record<Severity, number>;
  /** Empty means "show everything"; otherwise only these severities. */
  active: Set<Severity>;
  onToggleSeverity: (severity: Severity) => void;
  query: string;
  onQueryChange: (query: string) => void;
  onExpandAll: () => void;
  onCollapseAll: () => void;
}

/**
 * The bar that pins above the stacked files: what is in this review, and the
 * two controls a reviewer reaches for - narrow to a severity, or find a file.
 *
 * The severity counts double as the filter. They already have to be on screen,
 * and a number you can press is a smaller interface than a number plus a
 * separate filter menu.
 */
export function ReviewToolbar({
  fileCount,
  counts,
  active,
  onToggleSeverity,
  query,
  onQueryChange,
  onExpandAll,
  onCollapseAll,
}: ReviewToolbarProps) {
  const present = SEVERITY_ORDER.filter((severity) => counts[severity] > 0);

  return (
    <div className="bg-background/85 border-border-default sticky top-[var(--app-header-height)] z-30 -mx-4 mb-4 border-b px-4 py-2.5 backdrop-blur">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <p className="text-sm font-medium tabular-nums">
          {fileCount} dosya
          {present.length === 0 && <span className="text-muted"> · bulgu yok</span>}
        </p>

        {present.length > 0 && (
          <ul className="flex flex-wrap items-center gap-1.5">
            {present.map((severity) => {
              const isActive = active.has(severity);
              return (
                <li key={severity}>
                  <button
                    type="button"
                    aria-pressed={isActive}
                    onClick={() => onToggleSeverity(severity)}
                    className={cn(
                      'inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs transition-colors',
                      isActive
                        ? 'border-accent bg-accent-soft text-foreground font-medium'
                        : 'border-border-default text-muted hover:border-accent-ring hover:text-foreground',
                    )}
                  >
                    <span
                      aria-hidden
                      className={cn('size-1.5 rounded-full', SEVERITY_FILL[severity])}
                    />
                    <span className="tabular-nums">{counts[severity]}</span>
                    {SEVERITY_LABEL[severity]}
                  </button>
                </li>
              );
            })}
          </ul>
        )}

        <div className="ml-auto flex items-center gap-2">
          <div className="relative">
            <Search
              aria-hidden
              className="text-muted pointer-events-none absolute top-1/2 left-2 size-3.5 -translate-y-1/2"
            />
            <input
              type="search"
              value={query}
              onChange={(event) => onQueryChange(event.target.value)}
              placeholder="Dosya ara…"
              aria-label="Dosya ara"
              className="border-border-default bg-surface placeholder:text-muted hover:border-accent-ring focus:border-accent h-7 w-40 rounded-md border pr-2 pl-7 text-xs transition-colors focus:outline-none sm:w-52"
            />
          </div>
          <Button size="sm" variant="ghost" onClick={onExpandAll}>
            Tümünü aç
          </Button>
          <Button size="sm" variant="ghost" onClick={onCollapseAll}>
            Tümünü kapat
          </Button>
        </div>
      </div>
    </div>
  );
}

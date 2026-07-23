'use client';

import { ChevronDown, ChevronRight } from 'lucide-react';
import { useMemo } from 'react';

import { CodeViewer } from '@/components/review/code-viewer';
import { Spinner } from '@/components/ui/primitives';
import { useFileContent } from '@/hooks/use-file-content';
import {
  LAYER_LABEL,
  SEVERITY_FILL,
  SEVERITY_LABEL,
  SEVERITY_ORDER,
} from '@/lib/display';
import type {
  Finding,
  FindingStatus,
  Layer,
  ReviewFileSummary,
  Severity,
} from '@/lib/types';
import { cn } from '@/lib/utils';

interface FileCardProps {
  reviewId: string;
  file: ReviewFileSummary;
  findings: Finding[];
  expanded: boolean;
  viewed: boolean;
  onToggleExpanded: () => void;
  onToggleViewed: () => void;
  onStatusChange: (finding: Finding, status: FindingStatus) => void;
  pendingId: string | undefined;
}

/**
 * One file in the stacked review, the way a pull request shows it: a pinned
 * header carrying the path and what is wrong inside, and the source below it
 * with findings threaded between the lines.
 *
 * Source is fetched only while the card is expanded, so a review of forty
 * files costs forty requests only if the reviewer actually opens forty files.
 */
export function FileCard({
  reviewId,
  file,
  findings,
  expanded,
  viewed,
  onToggleExpanded,
  onToggleViewed,
  onStatusChange,
  pendingId,
}: FileCardProps) {
  const { content, error } = useFileContent(reviewId, file.path, expanded);

  const counts = useMemo(() => {
    const map = new Map<Severity, number>();
    for (const finding of findings) {
      map.set(finding.severity, (map.get(finding.severity) ?? 0) + 1);
    }
    return SEVERITY_ORDER.filter((severity) => map.has(severity)).map((severity) => ({
      severity,
      count: map.get(severity) ?? 0,
    }));
  }, [findings]);

  const directory = file.path.includes('/')
    ? `${file.path.slice(0, file.path.lastIndexOf('/') + 1)}`
    : '';
  const basename = file.path.slice(file.path.lastIndexOf('/') + 1);

  return (
    <section
      id={anchorId(file.path)}
      // Read back by the tab's IntersectionObserver to tell the file tree
      // which file is currently on screen.
      data-path={file.path}
      // No `overflow-hidden` here, however much the rounded corners want it:
      // an overflowed ancestor becomes the sticky containing block, and the
      // header below would stop pinning. The corners are rounded per-child.
      // Scrolling to a file must not tuck its header under the sticky toolbar.
      className="border-border-default bg-surface-raised scroll-mt-[calc(var(--app-header-height)+var(--review-toolbar-height)+1rem)] rounded-lg border"
    >
      <header
        className={cn(
          'bg-surface border-border-default z-20 flex flex-wrap items-center gap-x-3 gap-y-2 rounded-t-lg border-b px-3 py-2',
          // Only pinned on wide screens: below `lg` the review toolbar wraps
          // to two rows, so the offset it would pin against is no longer true.
          'lg:sticky lg:top-[calc(var(--app-header-height)+var(--review-toolbar-height))]',
        )}
      >
        <button
          type="button"
          onClick={onToggleExpanded}
          aria-expanded={expanded}
          className="text-muted hover:text-foreground -m-1 flex min-w-0 items-center gap-2 rounded p-1 text-left transition-colors"
        >
          {expanded ? (
            <ChevronDown aria-hidden className="size-4 shrink-0" />
          ) : (
            <ChevronRight aria-hidden className="size-4 shrink-0" />
          )}
          <span className="min-w-0 truncate font-mono text-xs">
            {directory !== '' && <span className="text-muted">{directory}</span>}
            <span className="text-foreground font-medium">{basename}</span>
          </span>
        </button>

        <span className="text-muted hidden shrink-0 font-mono text-xs sm:inline">
          {file.line_count} satır
          {file.truncated && ' · kırpıldı'}
        </span>

        <div className="ml-auto flex shrink-0 items-center gap-3">
          {counts.length > 0 && (
            <ul className="flex items-center gap-2">
              {counts.map(({ severity, count }) => (
                <li
                  key={severity}
                  title={`${count} ${SEVERITY_LABEL[severity]}`}
                  className="text-muted flex items-center gap-1 text-xs tabular-nums"
                >
                  <span
                    aria-hidden
                    className={cn('size-1.5 rounded-full', SEVERITY_FILL[severity])}
                  />
                  {count}
                  <span className="sr-only">{SEVERITY_LABEL[severity]}</span>
                </li>
              ))}
            </ul>
          )}

          <label className="text-muted hover:text-foreground flex cursor-pointer items-center gap-1.5 text-xs transition-colors">
            <input
              type="checkbox"
              checked={viewed}
              onChange={onToggleViewed}
              className="accent-accent size-3.5"
            />
            Görüldü
          </label>
        </div>
      </header>

      {/* Clipping lives on this wrapper rather than on the section, so the
          bottom corners round without disabling the sticky header above. */}
      <div className="overflow-hidden rounded-b-lg">
        {expanded &&
          (error !== undefined ? (
            <p className="text-danger px-4 py-6 text-sm">{error}</p>
          ) : content === undefined ? (
            <p className="text-muted flex items-center gap-2 px-4 py-6 text-sm">
              <Spinner />
              Dosya yükleniyor…
            </p>
          ) : (
            <CodeViewer
              file={content}
              findings={findings}
              pendingId={pendingId}
              onStatusChange={onStatusChange}
            />
          ))}

        {!expanded && (
          <p className="text-muted px-4 py-2.5 text-xs">
            {file.layers.map((layer) => LAYER_LABEL[layer as Layer] ?? layer).join(' · ')}
            {findings.length > 0 && ` · ${findings.length} bulgu`}
          </p>
        )}
      </div>
    </section>
  );
}

/** Stable DOM id so the file tree can scroll straight to a card. */
export function anchorId(path: string): string {
  return `file-${path.replace(/[^a-zA-Z0-9]/g, '-')}`;
}

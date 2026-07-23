'use client';

import { Check, FileCode } from 'lucide-react';

import { SEVERITY_FILL, SEVERITY_LABEL } from '@/lib/display';
import type { ReviewFileSummary, Severity } from '@/lib/types';
import { cn } from '@/lib/utils';

interface FileTreeProps {
  files: ReviewFileSummary[];
  /** Worst severity found in each file, keyed by path. */
  worstByPath: Map<string, Severity>;
  viewed: ReadonlySet<string>;
  /** The file currently filling the viewport. */
  activePath: string | undefined;
  onSelect: (path: string) => void;
}

/**
 * Sidebar file list. Selecting an entry scrolls to that file's card rather
 * than swapping the pane, because in a stacked review every file is already
 * on the page - the tree is a map, not a switch.
 */
export function FileTree({
  files,
  worstByPath,
  viewed,
  activePath,
  onSelect,
}: FileTreeProps) {
  return (
    <nav aria-label="İncelenen dosyalar" className="flex flex-col">
      {files.map((file) => {
        const isActive = file.path === activePath;
        const worst = worstByPath.get(file.path);
        const isViewed = viewed.has(file.path);
        const basename = file.path.slice(file.path.lastIndexOf('/') + 1);
        const directory = file.path.slice(0, file.path.lastIndexOf('/') + 1);

        return (
          <button
            key={file.path}
            type="button"
            onClick={() => onSelect(file.path)}
            aria-current={isActive ? 'true' : undefined}
            className={cn(
              'flex items-start gap-2 border-l-2 px-3 py-2 text-left transition-colors',
              isActive
                ? 'border-l-accent bg-accent-soft'
                : 'hover:bg-surface-overlay border-l-transparent',
              isViewed && !isActive && 'opacity-55',
            )}
          >
            {isViewed ? (
              <Check aria-hidden className="text-verified mt-0.5 size-4 shrink-0" />
            ) : (
              <FileCode aria-hidden className="text-muted mt-0.5 size-4 shrink-0" />
            )}

            <span className="min-w-0 flex-1">
              <span className="block truncate font-mono text-xs">
                {directory !== '' && <span className="text-muted">{directory}</span>}
                <span className={cn(isActive ? 'text-foreground font-medium' : '')}>
                  {basename}
                </span>
              </span>
              {worst !== undefined && (
                <span className="text-muted mt-0.5 block text-xs">
                  en yüksek: {SEVERITY_LABEL[worst].toLocaleLowerCase('tr')}
                </span>
              )}
            </span>

            {file.finding_count > 0 && worst !== undefined && (
              <span className="mt-0.5 flex shrink-0 items-center gap-1.5">
                <span
                  aria-hidden
                  className={cn('size-1.5 rounded-full', SEVERITY_FILL[worst])}
                />
                <span className="text-muted text-xs tabular-nums">
                  {file.finding_count}
                </span>
              </span>
            )}
          </button>
        );
      })}
    </nav>
  );
}

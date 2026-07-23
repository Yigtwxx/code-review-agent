'use client';

import { Fragment, useMemo } from 'react';

import { FindingThread } from '@/components/review/finding-thread';
import { useHighlightedLines } from '@/hooks/use-highlighted-lines';
import { SEVERITY_FILL, SEVERITY_ORDER } from '@/lib/display';
import type { FileContent, Finding, FindingStatus, Severity } from '@/lib/types';
import { cn } from '@/lib/utils';

interface CodeViewerProps {
  file: FileContent;
  findings: Finding[];
  onStatusChange: (finding: Finding, status: FindingStatus) => void;
  pendingId?: string;
}

/**
 * The review surface: numbered source with findings threaded in below the line
 * they refer to, like comments on a pull request diff.
 *
 * In pull-request mode only changed lines carry the "added" tint, so the eye
 * goes to what this pull request is responsible for. The file's own header is
 * not drawn here - the surrounding file card owns it, so it can stay pinned
 * while this table scrolls past.
 */
export function CodeViewer({
  file,
  findings,
  onStatusChange,
  pendingId,
}: CodeViewerProps) {
  const lines = useMemo(() => file.content.split('\n'), [file.content]);
  const tokens = useHighlightedLines(file.content, file.language);

  const changed = useMemo(() => {
    if (file.hunks === undefined || file.hunks === null) return undefined;
    return new Set(file.hunks.flatMap((hunk) => hunk.changed_lines));
  }, [file.hunks]);

  /** Findings keyed by the line their thread is rendered under. */
  const byLine = useMemo(() => {
    const map = new Map<number, Finding[]>();
    for (const finding of findings) {
      const line = Math.min(Math.max(finding.line_start, 1), lines.length);
      const bucket = map.get(line);
      if (bucket === undefined) map.set(line, [finding]);
      else bucket.push(finding);
    }
    for (const bucket of map.values()) {
      bucket.sort(
        (a, b) => SEVERITY_ORDER.indexOf(a.severity) - SEVERITY_ORDER.indexOf(b.severity),
      );
    }
    return map;
  }, [findings, lines.length]);

  /**
   * The gutter rail covers a finding's whole range, not just the line its
   * thread hangs off. A five-line function with one comment under it is still
   * five lines of problem, and the rail should say so.
   */
  const railByLine = useMemo(() => {
    const map = new Map<number, Severity>();
    for (const finding of findings) {
      const start = Math.min(Math.max(finding.line_start, 1), lines.length);
      const end = Math.min(Math.max(finding.line_end, start), lines.length);
      for (let line = start; line <= end; line += 1) {
        const current = map.get(line);
        if (
          current === undefined ||
          SEVERITY_ORDER.indexOf(finding.severity) < SEVERITY_ORDER.indexOf(current)
        ) {
          map.set(line, finding.severity);
        }
      }
    }
    return map;
  }, [findings, lines.length]);

  const gutterWidth = `${String(lines.length).length + 1}ch`;

  return (
    <div className="bg-code-background overflow-x-auto">
      <table className="w-full border-collapse">
        <tbody className="code-surface">
          {lines.map((line, index) => {
            const number = index + 1;
            const threads = byLine.get(number);
            const isChanged = changed?.has(number) ?? false;
            const rail = railByLine.get(number);

            return (
              <Fragment key={number}>
                <tr
                  id={`L${number}`}
                  className={cn(
                    'group',
                    isChanged && 'bg-line-added',
                    rail !== undefined && 'bg-line-highlight',
                  )}
                >
                  <td
                    className="text-muted group-hover:text-foreground relative py-0 pr-3 pl-3 text-right align-top transition-colors select-none"
                    style={{ width: gutterWidth }}
                  >
                    {rail !== undefined && (
                      <span
                        aria-hidden
                        className={cn(
                          'absolute top-0 bottom-0 left-0 w-[3px]',
                          SEVERITY_FILL[rail],
                        )}
                      />
                    )}
                    {number}
                  </td>
                  <td className="group-hover:bg-surface/40 w-full py-0 pr-4 align-top whitespace-pre transition-colors">
                    {tokens?.[index] !== undefined
                      ? tokens[index].map((token, tokenIndex) => (
                          <span key={tokenIndex} style={{ color: token.color }}>
                            {token.content}
                          </span>
                        ))
                      : line}
                  </td>
                </tr>

                {threads?.map((finding) => (
                  <tr key={finding.id}>
                    <td colSpan={2} className="p-0">
                      <FindingThread
                        finding={finding}
                        busy={pendingId === finding.id}
                        onStatusChange={(status) => onStatusChange(finding, status)}
                      />
                    </td>
                  </tr>
                ))}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

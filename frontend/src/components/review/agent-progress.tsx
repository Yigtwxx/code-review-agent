'use client';

import { Check, Loader2 } from 'lucide-react';

import { Spinner } from '@/components/ui/primitives';
import type { StageProgress } from '@/hooks/use-review-socket';
import { cn } from '@/lib/utils';

/**
 * Live pipeline progress, in the spirit of a pull request's "checks running"
 * panel: which agent is working, and what it has found so far.
 *
 * Purely informational. If the socket never connects, the finished review is
 * still fetched over REST - nothing here is load-bearing.
 */
export function AgentProgress({
  stages,
  connected,
}: {
  stages: StageProgress[];
  connected: boolean;
}) {
  if (stages.length === 0) {
    return (
      <div className="border-border-default bg-surface text-muted flex items-center gap-2 rounded-lg border px-4 py-3 text-sm">
        <Spinner />
        {connected
          ? // Progress events are not replayed, so a client that connects
            // part-way through has genuinely missed the earlier stages.
            'İnceleme sürüyor. Bu bağlantıdan sonraki aşamalar burada görünecek.'
          : 'İlerleme akışına bağlanılıyor…'}
      </div>
    );
  }

  const running = stages.filter((stage) => stage.status === 'running').length;

  return (
    <section
      aria-label="İnceleme ilerlemesi"
      aria-live="polite"
      className="border-border-default overflow-hidden rounded-lg border"
    >
      <header className="border-border-default bg-surface flex items-center justify-between border-b px-4 py-2">
        <span className="text-sm font-medium">
          {running > 0 ? `${running} aşama çalışıyor` : 'Aşamalar tamamlandı'}
        </span>
        <span className="text-muted font-mono text-xs tabular-nums">
          {stages.filter((s) => s.status === 'done').length}/{stages.length}
        </span>
      </header>

      <ul className="divide-border-muted divide-y">
        {stages.map((stage) => (
          <li
            key={stage.stage}
            className={cn(
              'bg-surface-raised flex items-center gap-3 px-4 py-2',
              stage.status === 'running' && 'bg-accent-soft',
            )}
          >
            {stage.status === 'running' ? (
              <Loader2 aria-hidden className="text-accent size-4 shrink-0 animate-spin" />
            ) : (
              <Check aria-hidden className="text-verified size-4 shrink-0" />
            )}
            <span
              className={cn(
                'font-mono text-xs',
                stage.status === 'running' ? 'text-foreground font-medium' : 'text-muted',
              )}
            >
              {stage.stage}
            </span>
            <span className="text-muted ml-auto truncate text-xs">{stage.message}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

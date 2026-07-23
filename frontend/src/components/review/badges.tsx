import { ShieldCheck, Sparkles, Terminal } from 'lucide-react';

import {
  LENS_LABEL,
  ORIGIN_HINT,
  ORIGIN_LABEL,
  SEVERITY_CLASS,
  SEVERITY_LABEL,
} from '@/lib/display';
import type { Origin, Severity } from '@/lib/types';
import { cn } from '@/lib/utils';

export function SeverityPill({
  severity,
  className,
}: {
  severity: Severity;
  className?: string;
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ring-1 ring-inset',
        SEVERITY_CLASS[severity],
        className,
      )}
    >
      {SEVERITY_LABEL[severity]}
    </span>
  );
}

/**
 * Which agent raised a finding, and through which lens.
 *
 * Shown on every agent finding because "who said this" is the first thing a
 * reviewer wants when deciding how much weight to give a comment.
 */
export function AgentBadge({ agent, lens }: { agent: string; lens?: string }) {
  return (
    <span className="text-muted inline-flex items-center gap-1.5 text-xs">
      <Sparkles aria-hidden className="text-muted size-3.5" />
      <span className="text-foreground font-medium">{agent}</span>
      {lens !== undefined && (
        <span className="text-muted">
          · {LENS_LABEL[lens as keyof typeof LENS_LABEL] ?? lens}
        </span>
      )}
    </span>
  );
}

export function ToolBadge({ tool, ruleId }: { tool: string; ruleId?: string }) {
  return (
    <span className="text-muted inline-flex items-center gap-1.5 text-xs">
      <Terminal aria-hidden className="size-3.5" />
      <span className="text-foreground font-medium">{tool}</span>
      {ruleId !== undefined && <code className="text-muted font-mono">{ruleId}</code>}
    </span>
  );
}

/**
 * The provenance chip - the visible payoff of hybrid validation.
 *
 * Teal is spent here and nowhere else in the palette, so corroboration reads
 * at a glance: a reviewer can tell whether a deterministic tool independently
 * confirmed the model, which is exactly what decides how sceptically to read
 * the comment.
 */
export function CorroborationBadge({
  origin,
  corroboratedBy,
}: {
  origin: Origin;
  corroboratedBy: string[];
}) {
  if (origin === 'hybrid' && corroboratedBy.length > 0) {
    return (
      <span
        title={ORIGIN_HINT.hybrid}
        className="bg-verified-soft text-verified ring-verified-ring inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-semibold ring-1 ring-inset"
      >
        <ShieldCheck aria-hidden className="size-3.5" />
        {corroboratedBy.join(', ')} doğruladı
      </span>
    );
  }

  if (origin === 'llm') {
    return (
      <span
        title={ORIGIN_HINT.llm}
        className="text-muted border-border-default inline-flex items-center rounded-full border border-dashed px-2 py-0.5 text-xs font-medium"
      >
        Statik doğrulama yok
      </span>
    );
  }

  return (
    <span
      title={ORIGIN_HINT.static}
      className="bg-surface text-muted ring-border-default inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset"
    >
      {ORIGIN_LABEL.static}
    </span>
  );
}

export function MetaChip({ children }: { children: React.ReactNode }) {
  return (
    <span className="bg-surface text-muted border-border-muted inline-flex items-center rounded-md border px-1.5 py-0.5 font-mono text-xs">
      {children}
    </span>
  );
}

'use client';

import { Check, ChevronDown, ChevronRight, X } from 'lucide-react';
import { useState } from 'react';

import {
  AgentBadge,
  CorroborationBadge,
  MetaChip,
  SeverityPill,
  ToolBadge,
} from '@/components/review/badges';
import { Button } from '@/components/ui/primitives';
import { categoryLabel } from '@/lib/display';
import type { Finding, FindingStatus } from '@/lib/types';
import { cn } from '@/lib/utils';

interface FindingThreadProps {
  finding: Finding;
  onStatusChange: (status: FindingStatus) => void;
  busy?: boolean;
}

/**
 * One finding, rendered as an inline review comment under the line it targets -
 * the same place a human reviewer's comment would appear on a pull request.
 *
 * The left rail says how well corroborated the claim is, and nothing else: a
 * teal solid rail means a deterministic tool reproduced the finding, a neutral
 * solid rail means it stands on a tool or a model alone, and a broken rail
 * means only the model ever asserted it. An unverified finding literally looks
 * unfinished. Severity stays on the pill and the gutter bar, so the rail is
 * never repeating something already on screen.
 */
export function FindingThread({ finding, onStatusChange, busy }: FindingThreadProps) {
  const [showFix, setShowFix] = useState(false);
  const resolved = finding.status !== 'open';
  const corroborated = finding.origin === 'hybrid' && finding.corroborated_by.length > 0;
  const modelOnly = finding.origin === 'llm';

  return (
    <div
      style={{
        // Provenance only - see `.rail` in globals.css for why not severity.
        ['--rail-color' as string]: corroborated ? 'var(--verified)' : 'var(--border)',
      }}
      className={cn(
        'bg-surface border-border-muted border-y py-3 pr-4 pl-4',
        modelOnly ? 'rail-dashed' : 'rail',
        resolved && 'opacity-55',
      )}
    >
      <div className="flex flex-wrap items-center gap-2">
        <SeverityPill severity={finding.severity} />
        <span className="text-sm font-semibold">{finding.title}</span>
        {resolved && (
          <span className="bg-surface-overlay text-muted ring-border-default rounded-full px-2 py-0.5 text-xs ring-1 ring-inset">
            {finding.status === 'dismissed' ? 'Yok sayıldı' : 'Çözüldü'}
          </span>
        )}
      </div>

      <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
        {/* A static-only finding arrives with `agent: null`, so the branch has
            to test for null as well or it renders a nameless agent badge. */}
        {finding.agent != null ? (
          <AgentBadge agent={finding.agent} lens={finding.lens} />
        ) : (
          finding.tool != null && (
            <ToolBadge tool={finding.tool} ruleId={finding.rule_id ?? undefined} />
          )
        )}
        <CorroborationBadge
          origin={finding.origin}
          corroboratedBy={finding.corroborated_by}
        />
      </div>

      <p className="text-foreground mt-2.5 max-w-3xl text-sm leading-relaxed">
        {finding.explanation}
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-1.5">
        <MetaChip>{categoryLabel(finding.category)}</MetaChip>
        {/* The API sends `null`, not `undefined`, when a finding carries no
            classification - an `undefined` check alone renders empty chips. */}
        {finding.owasp != null && finding.owasp !== '' && (
          <MetaChip>{finding.owasp}</MetaChip>
        )}
        {finding.cwe != null && finding.cwe !== '' && <MetaChip>{finding.cwe}</MetaChip>}
        <MetaChip>güven {(finding.confidence * 100).toFixed(0)}%</MetaChip>
        <MetaChip>
          satır {finding.line_start}
          {finding.line_end !== finding.line_start && `–${finding.line_end}`}
        </MetaChip>
      </div>

      {finding.suggested_fix !== undefined && finding.suggested_fix !== null && (
        <div className="mt-3">
          <button
            type="button"
            onClick={() => setShowFix((open) => !open)}
            aria-expanded={showFix}
            className="text-accent hover:text-accent-hover inline-flex items-center gap-1 text-xs font-medium transition-colors"
          >
            {showFix ? (
              <ChevronDown aria-hidden className="size-3.5" />
            ) : (
              <ChevronRight aria-hidden className="size-3.5" />
            )}
            Önerilen düzeltme
          </button>
          {showFix && (
            <pre className="code-surface bg-verified-soft border-verified-ring text-foreground mt-2 overflow-x-auto rounded-md border p-3">
              <code>{finding.suggested_fix}</code>
            </pre>
          )}
        </div>
      )}

      <div className="mt-3 flex gap-2">
        {finding.status === 'open' ? (
          <>
            <Button
              size="sm"
              variant="secondary"
              disabled={busy}
              onClick={() => onStatusChange('resolved')}
            >
              <Check aria-hidden className="size-3.5" />
              Çözüldü olarak işaretle
            </Button>
            <Button
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() => onStatusChange('dismissed')}
            >
              <X aria-hidden className="size-3.5" />
              Yok say
            </Button>
          </>
        ) : (
          <Button
            size="sm"
            variant="ghost"
            disabled={busy}
            onClick={() => onStatusChange('open')}
          >
            Yeniden aç
          </Button>
        )}
      </div>
    </div>
  );
}

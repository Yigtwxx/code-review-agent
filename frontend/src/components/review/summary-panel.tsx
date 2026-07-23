'use client';

import { Card } from '@/components/ui/primitives';
import {
  LAYER_LABEL,
  SEVERITY_CLASS,
  SEVERITY_FILL,
  SEVERITY_LABEL,
  SEVERITY_ORDER,
  riskLabel,
} from '@/lib/display';
import type { Layer, ReviewDetail } from '@/lib/types';
import { cn, formatDuration } from '@/lib/utils';

export function SummaryPanel({ review }: { review: ReviewDetail }) {
  const { stats } = review;
  const risk = riskLabel(review.risk_score);
  const total = SEVERITY_ORDER.reduce(
    (sum, severity) => sum + (stats.by_severity[severity] ?? 0),
    0,
  );
  // A score of zero means "nothing found *yet*" until the run ends. Showing a
  // green all-clear mid-review would be a lie the reviewer might act on.
  const settled = review.status === 'completed';

  const corroborated = stats.by_origin.hybrid ?? 0;
  const modelOnly = stats.by_origin.llm ?? 0;
  const staticOnly = stats.by_origin.static ?? 0;

  return (
    <Card className="p-4">
      <h2 className="text-eyebrow">İnceleme özeti</h2>

      <div className="mt-3 flex items-center gap-3">
        <RiskDial score={settled ? review.risk_score : undefined} color={risk.color} />
        <div className="min-w-0">
          {settled ? (
            <>
              <p className={cn('text-2xl font-semibold tabular-nums', risk.className)}>
                {review.risk_score}
                <span className="text-muted ml-1 text-sm font-normal">/100</span>
              </p>
              <p className={cn('text-xs', risk.className)}>{risk.label}</p>
            </>
          ) : (
            <>
              <p className="text-muted text-2xl font-semibold tabular-nums">—</p>
              <p className="text-muted text-xs">
                {review.status === 'failed'
                  ? 'İnceleme tamamlanamadı'
                  : 'İnceleme sürüyor, skor henüz kesin değil'}
              </p>
            </>
          )}
        </div>
      </div>

      {total > 0 && (
        <div
          className="bg-surface mt-4 flex h-1.5 gap-px overflow-hidden rounded-full"
          role="img"
          aria-label={SEVERITY_ORDER.filter((s) => stats.by_severity[s])
            .map((s) => `${stats.by_severity[s]} ${SEVERITY_LABEL[s]}`)
            .join(', ')}
        >
          {SEVERITY_ORDER.map((severity) => {
            const count = stats.by_severity[severity] ?? 0;
            if (count === 0) return null;
            return (
              <span
                key={severity}
                className={SEVERITY_FILL[severity]}
                style={{ width: `${(count / total) * 100}%` }}
              />
            );
          })}
        </div>
      )}

      <dl className="mt-4 space-y-1.5 text-xs">
        {SEVERITY_ORDER.filter((s) => (stats.by_severity[s] ?? 0) > 0).map((severity) => (
          <div key={severity} className="flex items-center justify-between gap-2">
            <dt>
              <span
                className={cn(
                  'rounded-full px-1.5 py-0.5 font-medium ring-1 ring-inset',
                  SEVERITY_CLASS[severity],
                )}
              >
                {SEVERITY_LABEL[severity]}
              </span>
            </dt>
            <dd className="tabular-nums">{stats.by_severity[severity]}</dd>
          </div>
        ))}
      </dl>

      {settled && (
        <>
          <hr className="border-border-muted my-4" />

          <h3 className="text-eyebrow">Kanıt kaynağı</h3>
          <dl className="mt-2 space-y-1.5 text-xs">
            <Row
              label="Ajan + statik doğrulama"
              value={corroborated}
              hint="Hem dil modeli hem bağımsız bir araç aynı kusuru buldu."
              emphasis
            />
            <Row
              label="Yalnızca statik analiz"
              value={staticOnly}
              hint="Deterministik bir kural eşleşti."
            />
            <Row
              label="Yalnızca ajan"
              value={modelOnly}
              hint="Statik araçların göremediği bulgular; daha temkinli okunmalı."
            />
            {stats.suppressed_low_confidence > 0 && (
              <Row
                label="Elenen düşük güvenli"
                value={stats.suppressed_low_confidence}
                hint="Model güveni eşiğin altındaydı ve hiçbir araç doğrulamadı."
              />
            )}
          </dl>
        </>
      )}

      {Object.keys(stats.by_layer).length > 0 && (
        <>
          <hr className="border-border-muted my-4" />
          <h3 className="text-eyebrow">Katman dağılımı</h3>
          <dl className="mt-2 space-y-1.5 text-xs">
            {Object.entries(stats.by_layer)
              .sort((a, b) => b[1] - a[1])
              .map(([layer, count]) => (
                <div key={layer} className="flex items-center justify-between gap-2">
                  <dt className="text-muted">{LAYER_LABEL[layer as Layer] ?? layer}</dt>
                  <dd className="tabular-nums">{count}</dd>
                </div>
              ))}
          </dl>
        </>
      )}

      <hr className="border-border-muted my-4" />

      <dl className="text-muted space-y-1.5 text-xs">
        <div className="flex justify-between gap-2">
          <dt>Model</dt>
          <dd className="text-foreground truncate font-mono">{review.llm_model}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt>Dosya</dt>
          <dd className="text-foreground tabular-nums">
            {stats.files_analysed || review.files.length}
          </dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt>Süre</dt>
          <dd className="text-foreground tabular-nums">
            {formatDuration(review.duration_ms)}
          </dd>
        </div>
      </dl>
    </Card>
  );
}

/**
 * The risk score as an arc rather than a bar: a score out of 100 is a fraction
 * of a whole, and the arc says so without needing the "/100" to be read.
 */
function RiskDial({ score, color }: { score: number | undefined; color: string }) {
  const radius = 20;
  const circumference = 2 * Math.PI * radius;
  const filled = score === undefined ? 0 : (Math.min(score, 100) / 100) * circumference;

  return (
    <svg
      aria-hidden
      viewBox="0 0 48 48"
      className="size-12 shrink-0 -rotate-90"
      fill="none"
    >
      <circle
        cx="24"
        cy="24"
        r={radius}
        stroke="var(--border)"
        strokeWidth="4"
        strokeLinecap="round"
      />
      {score !== undefined && score > 0 && (
        <circle
          cx="24"
          cy="24"
          r={radius}
          stroke={color}
          strokeWidth="4"
          strokeLinecap="round"
          strokeDasharray={`${filled} ${circumference}`}
        />
      )}
    </svg>
  );
}

function Row({
  label,
  value,
  hint,
  emphasis,
}: {
  label: string;
  value: number;
  hint: string;
  emphasis?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-2">
      <dt className={emphasis === true ? 'text-verified' : 'text-muted'} title={hint}>
        {label}
      </dt>
      <dd
        className={cn('tabular-nums', emphasis === true && 'text-verified font-semibold')}
      >
        {value}
      </dd>
    </div>
  );
}

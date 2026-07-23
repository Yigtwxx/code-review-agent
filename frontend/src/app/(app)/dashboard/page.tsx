'use client';

import { GitPullRequest, Upload, FileText, Terminal } from 'lucide-react';
import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';

import { Alert, Card, EmptyState, Spinner, Button } from '@/components/ui/primitives';
import { api } from '@/lib/api';
import { SEVERITY_FILL, SEVERITY_LABEL, SEVERITY_ORDER, riskLabel } from '@/lib/display';
import type { ReviewSummary } from '@/lib/types';
import { cn, formatDuration, formatRelativeTime } from '@/lib/utils';

const SOURCE_ICON = {
  upload: Upload,
  paste: FileText,
  pull_request: GitPullRequest,
  ci: Terminal,
} as const;

const STATUS_LABEL = {
  queued: 'Sırada',
  running: 'Çalışıyor',
  completed: 'Tamamlandı',
  failed: 'Başarısız',
} as const;

export default function DashboardPage() {
  const [reviews, setReviews] = useState<ReviewSummary[] | undefined>(undefined);
  const [error, setError] = useState<string | undefined>(undefined);

  // State is set from the promise callback, and a cancelled flag stops a slow
  // response from overwriting newer state after the user navigates away.
  const load = useCallback(
    (isCancelled: () => boolean = () => false) =>
      api
        .listReviews()
        .then((loaded) => {
          if (!isCancelled()) setReviews(loaded);
        })
        .catch(() => {
          if (!isCancelled()) setError('İncelemeler yüklenemedi.');
        }),
    [],
  );

  useEffect(() => {
    let cancelled = false;
    void load(() => cancelled);
    return () => {
      cancelled = true;
    };
  }, [load]);

  // A queued or running review finishes in the background; poll until it lands.
  useEffect(() => {
    const pending = reviews?.some(
      (review) => review.status === 'queued' || review.status === 'running',
    );
    if (pending !== true) return;
    const timer = setInterval(() => void load(), 4000);
    return () => clearInterval(timer);
  }, [reviews, load]);

  return (
    <div className="mx-auto max-w-[1400px] px-4 py-8">
      <div className="mb-6 flex items-center justify-between gap-4">
        <div>
          <h1 className="text-title">İncelemeler</h1>
          <p className="text-muted mt-1 text-sm">
            Yüklediğin kod katmanlara ayrılır ve her katmana ayrı bir ajan bakar.
          </p>
        </div>
      </div>

      {error !== undefined && <Alert>{error}</Alert>}

      {reviews === undefined ? (
        <div className="text-muted flex items-center gap-2 py-12 text-sm">
          <Spinner />
          Yükleniyor…
        </div>
      ) : reviews.length === 0 ? (
        <EmptyState
          title="Henüz inceleme yok"
          description="Bir dosya yükle, kod yapıştır ya da bir GitHub pull request adresi ver; sistem güvenlik ve kalite ajanlarını çalıştırsın."
          action={
            <Link href="/reviews/new" className="mt-2">
              <Button variant="primary" size="sm">
                İlk incelemeyi başlat
              </Button>
            </Link>
          }
        />
      ) : (
        <ul className="flex flex-col gap-2">
          {reviews.map((review) => (
            <li key={review.id}>
              <ReviewRow review={review} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ReviewRow({ review }: { review: ReviewSummary }) {
  const Icon = SOURCE_ICON[review.source.kind];
  const risk = riskLabel(review.risk_score);
  const total = SEVERITY_ORDER.reduce(
    (sum, severity) => sum + (review.stats.by_severity[severity] ?? 0),
    0,
  );
  const inFlight = review.status === 'queued' || review.status === 'running';

  return (
    <Link href={`/reviews/${review.id}`} className="block">
      <Card className="hover:border-accent-ring hover:bg-surface-overlay flex items-center gap-4 p-4 transition-colors">
        <Icon aria-hidden className="text-muted size-5 shrink-0" />

        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium">
            {review.source.label || 'İsimsiz inceleme'}
          </p>
          <p className="text-muted mt-0.5 flex flex-wrap items-center gap-x-2 text-xs">
            <span>{formatRelativeTime(review.created_at)}</span>
            <span aria-hidden>·</span>
            <span className="font-mono">{review.llm_model}</span>
            {review.duration_ms !== undefined && review.duration_ms !== null && (
              <>
                <span aria-hidden>·</span>
                <span className="tabular-nums">{formatDuration(review.duration_ms)}</span>
              </>
            )}
          </p>
        </div>

        {total > 0 && (
          <div className="hidden w-32 shrink-0 sm:block">
            <div className="bg-surface flex h-1.5 gap-px overflow-hidden rounded-full">
              {SEVERITY_ORDER.map((severity) => {
                const count = review.stats.by_severity[severity] ?? 0;
                if (count === 0) return null;
                return (
                  <span
                    key={severity}
                    title={`${count} ${SEVERITY_LABEL[severity]}`}
                    className={SEVERITY_FILL[severity]}
                    style={{ width: `${(count / total) * 100}%` }}
                  />
                );
              })}
            </div>
            <p className="text-muted mt-1 text-right text-xs tabular-nums">
              {total} bulgu
            </p>
          </div>
        )}

        <div className="w-28 shrink-0 text-right">
          {inFlight ? (
            <span className="text-accent inline-flex items-center gap-1.5 text-xs">
              <Spinner />
              {STATUS_LABEL[review.status]}
            </span>
          ) : review.status === 'failed' ? (
            <span className="text-danger text-xs font-medium">{STATUS_LABEL.failed}</span>
          ) : (
            <>
              <p className={cn('text-lg font-semibold tabular-nums', risk.className)}>
                {review.risk_score}
              </p>
              <p className={cn('text-xs', risk.className)}>{risk.label}</p>
            </>
          )}
        </div>
      </Card>
    </Link>
  );
}

/**
 * Presentation vocabulary: how severities, layers and provenance are shown.
 *
 * One module so a severity looks identical in the dashboard, the file tree and
 * an inline comment - the reviewer learns the colour once.
 */

import type { Layer, Lens, Origin, Severity } from '@/lib/types';

export const SEVERITY_ORDER: Severity[] = ['critical', 'high', 'medium', 'low', 'info'];

export const SEVERITY_LABEL: Record<Severity, string> = {
  critical: 'Kritik',
  high: 'Yüksek',
  medium: 'Orta',
  low: 'Düşük',
  info: 'Bilgi',
};

/**
 * Pill styling: the vivid hue as text on a wash of itself.
 *
 * Solid fills at this saturation would fight the code underneath, so the
 * colour reaches the eye through the type and the ring instead.
 */
export const SEVERITY_CLASS: Record<Severity, string> = {
  critical:
    'bg-severity-critical-soft text-severity-critical ring-severity-critical-ring',
  high: 'bg-severity-high-soft text-severity-high ring-severity-high-ring',
  medium: 'bg-severity-medium-soft text-severity-medium ring-severity-medium-ring',
  low: 'bg-severity-low-soft text-severity-low ring-severity-low-ring',
  info: 'bg-severity-info-soft text-severity-info ring-severity-info-ring',
};

/** Solid fill: gutter rails, distribution bars, status dots. */
export const SEVERITY_FILL: Record<Severity, string> = {
  critical: 'bg-severity-critical',
  high: 'bg-severity-high',
  medium: 'bg-severity-medium',
  low: 'bg-severity-low',
  info: 'bg-severity-info',
};

/** Text-only, for counts and inline emphasis. */
export const SEVERITY_TEXT: Record<Severity, string> = {
  critical: 'text-severity-critical',
  high: 'text-severity-high',
  medium: 'text-severity-medium',
  low: 'text-severity-low',
  info: 'text-severity-info',
};

export const LAYER_LABEL: Record<Layer, string> = {
  frontend: 'Frontend',
  backend: 'Backend',
  database: 'Veritabanı',
  config_infra: 'Config & Altyapı',
  generic: 'Genel',
};

export const LENS_LABEL: Record<Lens, string> = {
  security: 'güvenlik',
  quality: 'kalite',
};

export const ORIGIN_LABEL: Record<Origin, string> = {
  static: 'Statik analiz',
  llm: 'Ajan',
  hybrid: 'Ajan + statik doğrulama',
};

export const ORIGIN_HINT: Record<Origin, string> = {
  static: 'Deterministik bir araç tarafından bulundu.',
  llm: 'Yalnızca dil modeli tarafından raporlandı; statik araçlar doğrulamadı.',
  hybrid: 'Ajan raporladı ve bağımsız bir statik analiz aracı aynı kusuru doğruladı.',
};

export function riskLabel(score: number): {
  label: string;
  className: string;
  /** Stroke for the risk dial; a CSS colour, not a class. */
  color: string;
} {
  if (score >= 60)
    return {
      label: 'Kritik risk',
      className: 'text-severity-critical',
      color: 'var(--severity-critical)',
    };
  if (score >= 30)
    return {
      label: 'Yüksek risk',
      className: 'text-severity-high',
      color: 'var(--severity-high)',
    };
  if (score >= 10)
    return {
      label: 'Orta risk',
      className: 'text-severity-medium',
      color: 'var(--severity-medium)',
    };
  if (score > 0)
    return {
      label: 'Düşük risk',
      className: 'text-severity-low',
      color: 'var(--severity-low)',
    };
  return {
    label: 'Güvenlik bulgusu yok',
    className: 'text-verified',
    color: 'var(--verified)',
  };
}

/** Human-friendly name for a machine category slug. */
export function categoryLabel(category: string): string {
  return category.replace(/-/g, ' ').replace(/^\w/, (c) => c.toUpperCase());
}

import { describe, expect, it } from 'vitest';

import { categoryLabel, riskLabel, SEVERITY_ORDER } from '@/lib/display';
import { formatDuration, formatRelativeTime } from '@/lib/utils';

describe('riskLabel', () => {
  it('escalates the label as the score rises', () => {
    expect(riskLabel(0).label).toBe('Güvenlik bulgusu yok');
    expect(riskLabel(5).label).toBe('Düşük risk');
    expect(riskLabel(15).label).toBe('Orta risk');
    expect(riskLabel(40).label).toBe('Yüksek risk');
    expect(riskLabel(100).label).toBe('Kritik risk');
  });

  it('treats the boundary score as the higher band', () => {
    expect(riskLabel(10).label).toBe('Orta risk');
    expect(riskLabel(30).label).toBe('Yüksek risk');
    expect(riskLabel(60).label).toBe('Kritik risk');
  });
});

describe('severity ordering', () => {
  it('runs from most to least severe', () => {
    expect(SEVERITY_ORDER).toEqual(['critical', 'high', 'medium', 'low', 'info']);
  });
});

describe('categoryLabel', () => {
  it('turns a slug into readable text', () => {
    expect(categoryLabel('sql-injection')).toBe('Sql injection');
    expect(categoryLabel('hardcoded-secret')).toBe('Hardcoded secret');
  });
});

describe('formatDuration', () => {
  it('picks a unit that suits the magnitude', () => {
    expect(formatDuration(undefined)).toBe('—');
    expect(formatDuration(450)).toBe('450 ms');
    expect(formatDuration(2500)).toBe('2.5 sn');
    expect(formatDuration(125_000)).toBe('2 dk 5 sn');
  });
});

describe('formatRelativeTime', () => {
  it('describes recent timestamps in Turkish', () => {
    const now = new Date();
    expect(formatRelativeTime(now.toISOString())).toBe('az önce');

    const earlier = new Date(now.getTime() - 30 * 60_000);
    expect(formatRelativeTime(earlier.toISOString())).toBe('30 dakika önce');

    const yesterday = new Date(now.getTime() - 26 * 3_600_000);
    expect(formatRelativeTime(yesterday.toISOString())).toBe('1 gün önce');
  });
});

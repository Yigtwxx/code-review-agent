import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}

export function formatDuration(ms: number | null | undefined): string {
  // The API sends JSON null for a review that has not finished; treat that the
  // same as absent rather than rendering "null ms".
  if (ms === undefined || ms === null) return '—';
  if (ms < 1000) return `${ms} ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)} sn`;
  const minutes = Math.floor(seconds / 60);
  return `${minutes} dk ${Math.round(seconds % 60)} sn`;
}

export function formatRelativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  const diff = Date.now() - then;
  const minutes = Math.round(diff / 60_000);

  if (minutes < 1) return 'az önce';
  if (minutes < 60) return `${minutes} dakika önce`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} saat önce`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days} gün önce`;
  return new Date(iso).toLocaleDateString('tr-TR');
}

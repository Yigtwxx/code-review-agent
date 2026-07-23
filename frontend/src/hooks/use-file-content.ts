'use client';

import { useEffect, useState } from 'react';

import { api } from '@/lib/api';
import type { FileContent } from '@/lib/types';

/**
 * Source text for one file, fetched the first time it is asked for.
 *
 * The files-changed view stacks every file in one scroll, so fetching all of
 * them up front would mean one request per file for content most reviewers
 * never open. Instead a file card asks for its content only once it expands,
 * and the module-level cache means collapsing and reopening costs nothing.
 *
 * The cache is keyed by review too, so two reviews of the same path do not
 * show each other's source.
 */
const cache = new Map<string, FileContent>();
const inFlight = new Map<string, Promise<FileContent>>();

function load(reviewId: string, path: string): Promise<FileContent> {
  const key = `${reviewId}:${path}`;
  const cached = cache.get(key);
  if (cached !== undefined) return Promise.resolve(cached);

  // Two cards can mount and ask at once; one request answers both.
  const pending = inFlight.get(key);
  if (pending !== undefined) return pending;

  const request = api
    .getFile(reviewId, path)
    .then((content) => {
      cache.set(key, content);
      return content;
    })
    .finally(() => {
      inFlight.delete(key);
    });

  inFlight.set(key, request);
  return request;
}

interface FileContentState {
  content: FileContent | undefined;
  error: string | undefined;
}

/** What the last settled request produced, tagged with the file it was for. */
interface Settled extends FileContentState {
  key: string;
}

export function useFileContent(
  reviewId: string,
  path: string,
  enabled: boolean,
): FileContentState {
  const key = `${reviewId}:${path}`;
  const [settled, setSettled] = useState<Settled | undefined>(undefined);

  useEffect(() => {
    // Already cached: the read below serves it, and there is nothing to fetch.
    if (!enabled || cache.has(key)) return;

    let cancelled = false;
    void load(reviewId, path)
      .then((content) => {
        if (!cancelled) setSettled({ key, content, error: undefined });
      })
      .catch(() => {
        if (!cancelled) {
          setSettled({ key, content: undefined, error: 'Dosya içeriği yüklenemedi.' });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [reviewId, path, key, enabled]);

  // Read the cache during render rather than mirroring it into state: a file
  // that is already loaded should never flash empty on its way back.
  const cached = cache.get(key);
  if (cached !== undefined) return { content: cached, error: undefined };
  // A result tagged with a different file belongs to the previous path.
  if (settled?.key === key) return { content: settled.content, error: settled.error };
  return { content: undefined, error: undefined };
}

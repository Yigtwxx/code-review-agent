'use client';

import { useEffect, useState } from 'react';
import type { ThemedToken } from 'shiki';

/** Our backend language values mapped to Shiki grammar ids. */
const GRAMMAR: Record<string, string> = {
  python: 'python',
  typescript: 'typescript',
  tsx: 'tsx',
  javascript: 'javascript',
  jsx: 'jsx',
  sql: 'sql',
  yaml: 'yaml',
  json: 'json',
  dockerfile: 'docker',
  html: 'html',
  css: 'css',
  shell: 'shellscript',
};

/**
 * One theme, because the app has one theme. Night Owl's deep neutral ground
 * matches ours, and its tokens are vivid without leaning on a single hue -
 * which matters when the chrome around the code is deliberately colourless.
 */
const THEME = 'night-owl';

interface Highlighted {
  code: string;
  language: string;
  lines: ThemedToken[][];
}

/**
 * Tokenises source per line.
 *
 * Line-level tokens rather than a rendered HTML blob: the viewer has to
 * interleave finding threads between lines, which is impossible once Shiki has
 * produced one opaque `<pre>`.
 *
 * The result is stored together with the input it came from, so switching
 * files shows plain text for a moment rather than the previous file's
 * colours - and so no state is written synchronously during an effect.
 */
export function useHighlightedLines(
  code: string,
  language: string,
): ThemedToken[][] | undefined {
  const [result, setResult] = useState<Highlighted | undefined>(undefined);

  useEffect(() => {
    const grammar = GRAMMAR[language];
    if (grammar === undefined) return;

    let cancelled = false;

    void import('shiki')
      .then(({ codeToTokens }) =>
        codeToTokens(code, { lang: grammar as never, theme: THEME }),
      )
      .then((tokens) => {
        if (!cancelled) setResult({ code, language, lines: tokens.tokens });
      })
      .catch(() => {
        // Highlighting is a nicety; plain text is still perfectly reviewable.
      });

    return () => {
      cancelled = true;
    };
  }, [code, language]);

  return result?.code === code && result.language === language ? result.lines : undefined;
}

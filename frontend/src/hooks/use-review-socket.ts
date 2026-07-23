'use client';

import { useEffect, useRef, useState } from 'react';

import { API_BASE } from '@/lib/api';
import type { ReviewEvent, ReviewStatus } from '@/lib/types';

/** Progress of a single graph stage, as the UI shows it. */
export interface StageProgress {
  stage: string;
  status: 'running' | 'done';
  message: string;
  findingCount: number;
}

interface SocketState {
  events: ReviewEvent[];
  stages: StageProgress[];
  /** Set once the review reaches a terminal state over the socket. */
  terminal: ReviewStatus | undefined;
  connected: boolean;
}

const INITIAL: SocketState = {
  events: [],
  stages: [],
  terminal: undefined,
  connected: false,
};

function applyEvent(state: SocketState, event: ReviewEvent): SocketState {
  const stages = [...state.stages];
  const index = stages.findIndex((s) => s.stage === event.stage);

  if (event.type === 'node_started' && event.stage !== '') {
    const entry: StageProgress = {
      stage: event.stage,
      status: 'running',
      message: event.message,
      findingCount: 0,
    };
    if (index === -1) stages.push(entry);
    else stages[index] = { ...stages[index], ...entry };
  } else if (event.type === 'node_finished' && index !== -1) {
    stages[index] = {
      ...stages[index],
      status: 'done',
      message: event.message,
    };
  } else if (event.type === 'finding' && index !== -1) {
    stages[index] = {
      ...stages[index],
      findingCount: stages[index].findingCount + 1,
    };
  }

  const terminal =
    event.type === 'review_completed'
      ? 'completed'
      : event.type === 'review_failed'
        ? 'failed'
        : state.terminal;

  return {
    ...state,
    stages,
    terminal,
    // Keep the tail only: a long review would otherwise grow without bound.
    events: [...state.events, event].slice(-200),
  };
}

/**
 * Subscribes to a review's live progress.
 *
 * The socket is best-effort. It carries progress, never results - if it never
 * connects, the page still shows the finished review from the REST API.
 */
export function useReviewSocket(
  reviewId: string,
  enabled: boolean,
  token: string | undefined,
): SocketState {
  const [state, setState] = useState<SocketState>(INITIAL);
  const socketRef = useRef<WebSocket | undefined>(undefined);

  useEffect(() => {
    // The token is passed in rather than read from module state so the effect
    // re-runs when a page reload finishes restoring the session.
    if (!enabled || token === undefined) return;

    const url = new URL(`${API_BASE}/ws/reviews/${reviewId}`);
    url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
    url.searchParams.set('token', token);

    const socket = new WebSocket(url);
    socketRef.current = socket;

    socket.onopen = () => setState((s) => ({ ...s, connected: true }));
    socket.onclose = () => setState((s) => ({ ...s, connected: false }));
    socket.onmessage = (message) => {
      const parsed = JSON.parse(message.data as string) as
        ReviewEvent | { type: 'heartbeat' };
      if (parsed.type === 'heartbeat') return;
      setState((s) => applyEvent(s, parsed as ReviewEvent));
    };

    return () => {
      socketRef.current = undefined;
      socket.onopen = socket.onmessage = socket.onclose = null;
      // Closing a socket that is still CONNECTING throws the browser warning
      // "closed before the connection is established". Wait for it to open,
      // then close cleanly. Common on React strict-mode's dev double-mount and
      // when a fast review finishes before the socket settles.
      if (socket.readyState === WebSocket.CONNECTING) {
        socket.addEventListener('open', () => socket.close(), { once: true });
      } else {
        socket.close();
      }
    };
  }, [reviewId, enabled, token]);

  return state;
}

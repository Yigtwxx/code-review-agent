/**
 * Typed API client.
 *
 * The access token lives in memory only. Persisting it in `localStorage` would
 * make it readable by any injected script - the very class of bug this product
 * reports - so a page reload instead replays the httpOnly refresh cookie.
 */

import type {
  Capabilities,
  FileContent,
  Finding,
  FindingStatus,
  Patch,
  ReviewDetail,
  ReviewSummary,
  User,
} from '@/lib/types';

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? 'http://localhost:8001';

let accessToken: string | undefined;
/** De-duplicates concurrent refreshes so one 401 storm makes one call. */
let refreshInFlight: Promise<boolean> | undefined;

export function setAccessToken(token: string | undefined): void {
  accessToken = token;
}

export function getAccessToken(): string | undefined {
  return accessToken;
}

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

interface RequestOptions {
  method?: string;
  body?: unknown;
  /** Skip the refresh-and-retry dance; used by the refresh call itself. */
  raw?: boolean;
  signal?: AbortSignal;
}

async function readError(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown };
    if (typeof body.detail === 'string') return body.detail;
    if (Array.isArray(body.detail)) {
      // FastAPI validation errors arrive as a list of field problems.
      const first = body.detail[0] as { msg?: string } | undefined;
      if (first?.msg) return first.msg;
    }
  } catch {
    // Fall through to the status text.
  }
  return response.statusText || 'İstek başarısız oldu';
}

async function refreshAccessToken(): Promise<boolean> {
  refreshInFlight ??= (async () => {
    try {
      const response = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
        method: 'POST',
        credentials: 'include',
      });
      if (!response.ok) return false;
      const body = (await response.json()) as { access_token: string };
      accessToken = body.access_token;
      return true;
    } catch {
      return false;
    } finally {
      refreshInFlight = undefined;
    }
  })();
  return refreshInFlight;
}

async function send(path: string, options: RequestOptions): Promise<Response> {
  const headers: Record<string, string> = {};
  if (accessToken !== undefined) {
    headers.Authorization = `Bearer ${accessToken}`;
  }
  const isFormData = options.body instanceof FormData;
  if (options.body !== undefined && !isFormData) {
    headers['Content-Type'] = 'application/json';
  }

  return fetch(`${API_BASE}${path}`, {
    method: options.method ?? 'GET',
    credentials: 'include',
    headers,
    signal: options.signal,
    body: isFormData
      ? (options.body as FormData)
      : options.body !== undefined
        ? JSON.stringify(options.body)
        : undefined,
  });
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  let response = await send(path, options);

  // One silent retry: an expired access token should not surface as a logout.
  if (response.status === 401 && !options.raw && (await refreshAccessToken())) {
    response = await send(path, options);
  }

  if (!response.ok) {
    throw new ApiError(response.status, await readError(response));
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export const api = {
  async register(email: string, password: string): Promise<void> {
    const body = await request<TokenResponse>('/api/v1/auth/register', {
      method: 'POST',
      body: { email, password },
      raw: true,
    });
    accessToken = body.access_token;
  },

  async login(email: string, password: string): Promise<void> {
    const body = await request<TokenResponse>('/api/v1/auth/login', {
      method: 'POST',
      body: { email, password },
      raw: true,
    });
    accessToken = body.access_token;
  },

  async logout(): Promise<void> {
    await request('/api/v1/auth/logout', { method: 'POST' });
    accessToken = undefined;
  },

  /** Restores a session from the refresh cookie after a page reload. */
  async restoreSession(): Promise<User | undefined> {
    if (accessToken === undefined && !(await refreshAccessToken())) {
      return undefined;
    }
    try {
      return await api.me();
    } catch {
      accessToken = undefined;
      return undefined;
    }
  },

  me: (): Promise<User> => request<User>('/api/v1/auth/me'),

  updatePreferences: (body: {
    llm_model?: string;
    min_severity?: string;
    github_token?: string;
  }): Promise<User> => request<User>('/api/v1/auth/me', { method: 'PATCH', body }),

  capabilities: (): Promise<Capabilities> =>
    request<Capabilities>('/api/v1/system/capabilities'),

  listReviews: (): Promise<ReviewSummary[]> =>
    request<ReviewSummary[]>('/api/v1/reviews'),

  getReview: (id: string): Promise<ReviewDetail> =>
    request<ReviewDetail>(`/api/v1/reviews/${id}`),

  deleteReview: (id: string): Promise<void> =>
    request<void>(`/api/v1/reviews/${id}`, { method: 'DELETE' }),

  listFindings: (id: string): Promise<Finding[]> =>
    request<Finding[]>(`/api/v1/reviews/${id}/findings`),

  updateFinding: (
    reviewId: string,
    findingId: string,
    status: FindingStatus,
  ): Promise<Finding> =>
    request<Finding>(`/api/v1/reviews/${reviewId}/findings/${findingId}`, {
      method: 'PATCH',
      body: { status },
    }),

  getFile: (id: string, path: string): Promise<FileContent> =>
    request<FileContent>(
      `/api/v1/reviews/${id}/files/${path.split('/').map(encodeURIComponent).join('/')}`,
    ),

  listPatches: (id: string): Promise<Patch[]> =>
    request<Patch[]>(`/api/v1/reviews/${id}/patches`),

  /**
   * Fetch the refactored-code ZIP as an authenticated blob.
   *
   * A plain `<a href download>` navigation cannot carry the in-memory Bearer
   * token (and the refresh cookie is scoped to /auth), so it would 401. Going
   * through `send` attaches the token and reuses the silent 401 refresh-retry,
   * then the caller turns the blob into an object-URL download.
   */
  async downloadRefactored(id: string): Promise<{ blob: Blob; filename: string }> {
    const path = `/api/v1/reviews/${id}/download`;
    let response = await send(path, {});
    if (response.status === 401 && (await refreshAccessToken())) {
      response = await send(path, {});
    }
    if (!response.ok) {
      throw new ApiError(response.status, await readError(response));
    }
    const disposition = response.headers.get('Content-Disposition') ?? '';
    const match = disposition.match(/filename="?([^"]+)"?/);
    const filename = match?.[1] ?? `refactored-${id}.zip`;
    return { blob: await response.blob(), filename };
  },

  createFromPaste: (filename: string, content: string): Promise<ReviewSummary> =>
    request<ReviewSummary>('/api/v1/reviews/paste', {
      method: 'POST',
      body: { filename, content },
    }),

  createFromPullRequest: (url: string): Promise<ReviewSummary> =>
    request<ReviewSummary>('/api/v1/reviews/pull-request', {
      method: 'POST',
      body: { url },
    }),

  createFromUpload: (files: File[]): Promise<ReviewSummary> => {
    const form = new FormData();
    for (const file of files) form.append('files', file);
    return request<ReviewSummary>('/api/v1/reviews/upload', {
      method: 'POST',
      body: form,
    });
  },
};

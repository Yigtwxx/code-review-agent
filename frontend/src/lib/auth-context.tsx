'use client';

import { useRouter } from 'next/navigation';
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

import { api, getAccessToken } from '@/lib/api';
import type { User } from '@/lib/types';

interface AuthState {
  user: User | undefined;
  /** Mirrors the in-memory token so effects can depend on it arriving. */
  accessToken: string | undefined;
  /** True until the initial session restore settles. */
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | undefined>(undefined);
  const [accessToken, setAccessToken] = useState<string | undefined>(undefined);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  // The access token is memory-only, so a reload starts from the refresh
  // cookie rather than from a session the page could read back.
  useEffect(() => {
    let cancelled = false;
    void api.restoreSession().then((restored) => {
      if (!cancelled) {
        setUser(restored);
        setAccessToken(getAccessToken());
        setLoading(false);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    await api.login(email, password);
    setAccessToken(getAccessToken());
    setUser(await api.me());
  }, []);

  const register = useCallback(async (email: string, password: string) => {
    await api.register(email, password);
    setAccessToken(getAccessToken());
    setUser(await api.me());
  }, []);

  const logout = useCallback(async () => {
    await api.logout();
    setAccessToken(undefined);
    setUser(undefined);
    router.push('/login');
  }, [router]);

  const refreshUser = useCallback(async () => {
    setUser(await api.me());
  }, []);

  const value = useMemo(
    () => ({ user, accessToken, loading, login, register, logout, refreshUser }),
    [user, accessToken, loading, login, register, logout, refreshUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used inside an AuthProvider');
  }
  return context;
}

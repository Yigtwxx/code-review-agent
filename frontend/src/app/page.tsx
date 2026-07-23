'use client';

import { useRouter } from 'next/navigation';
import { useEffect } from 'react';

import { Spinner } from '@/components/ui/primitives';
import { useAuth } from '@/lib/auth-context';

export default function Home() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (loading) return;
    router.replace(user === undefined ? '/login' : '/dashboard');
  }, [user, loading, router]);

  return (
    <main
      id="main"
      className="text-muted flex flex-1 items-center justify-center gap-2 text-sm"
    >
      <Spinner />
      Yükleniyor…
    </main>
  );
}

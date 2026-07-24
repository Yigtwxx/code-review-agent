'use client';

import { Plus } from 'lucide-react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect } from 'react';

import { Logo } from '@/components/ui/logo';
import { Button, Spinner } from '@/components/ui/primitives';
import { useAuth } from '@/lib/auth-context';
import { cn } from '@/lib/utils';

const NAV = [
  { href: '/dashboard', label: 'İncelemeler' },
  { href: '/settings', label: 'Ayarlar' },
];

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, loading, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!loading && user === undefined) router.replace('/login');
  }, [user, loading, router]);

  if (loading || user === undefined) {
    return (
      <main className="text-muted flex flex-1 items-center justify-center gap-2 text-sm">
        <Spinner />
        Oturum kontrol ediliyor…
      </main>
    );
  }

  return (
    <div className="flex min-h-full flex-col">
      {/* Pinned: the review toolbar and every file header stack their sticky
          offsets on top of this, so its height is a token, not a guess. */}
      <header className="border-border-default bg-surface/90 sticky top-0 z-40 h-[var(--app-header-height)] border-b backdrop-blur">
        <div className="mx-auto flex h-full max-w-[1400px] items-center gap-3 px-4 sm:gap-6">
          {/* Below `sm` the mark stands in for the wordmark: the header is a
              fixed height, so nothing in it may wrap to a second line. */}
          <Link
            href="/dashboard"
            className="flex shrink-0 items-center gap-2 text-sm font-semibold whitespace-nowrap"
          >
            <Logo size={20} />
            <span className="sr-only sm:not-sr-only">Code Review Agent</span>
          </Link>

          <nav
            aria-label="Ana gezinme"
            className="flex h-full shrink-0 items-center gap-1"
          >
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                aria-current={pathname === item.href ? 'page' : undefined}
                className={cn(
                  'flex h-full items-center border-b-2 px-2.5 text-sm whitespace-nowrap transition-colors',
                  pathname === item.href
                    ? 'border-b-accent text-foreground font-semibold'
                    : 'text-muted hover:text-foreground border-b-transparent',
                )}
              >
                {item.label}
              </Link>
            ))}
          </nav>

          <div className="ml-auto flex shrink-0 items-center gap-2 sm:gap-3">
            <Link href="/reviews/new">
              <Button variant="primary" size="sm" aria-label="Yeni inceleme">
                <Plus aria-hidden className="size-3.5" />
                <span className="hidden whitespace-nowrap sm:inline">Yeni inceleme</span>
              </Button>
            </Link>
            <span className="text-muted hidden font-mono text-xs sm:inline">
              {user.email}
            </span>
            <Button size="sm" variant="ghost" onClick={() => void logout()}>
              Çıkış
            </Button>
          </div>
        </div>
      </header>

      <main id="main" className="flex-1">
        {children}
      </main>
    </div>
  );
}

'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState, type FormEvent } from 'react';
import { z } from 'zod';

import { Logo } from '@/components/ui/logo';
import { Alert, Button, Card, Field, Spinner } from '@/components/ui/primitives';
import { ApiError } from '@/lib/api';
import { useAuth } from '@/lib/auth-context';

const schema = z.object({
  email: z.string().email('Geçerli bir e-posta adresi girin'),
  password: z.string().min(8, 'Parola en az 8 karakter olmalı'),
});

type Mode = 'login' | 'register';

const COPY = {
  login: {
    title: 'Giriş yap',
    submit: 'Giriş yap',
    switchText: 'Hesabın yok mu?',
    switchLabel: 'Kayıt ol',
    switchHref: '/register',
  },
  register: {
    title: 'Kayıt ol',
    submit: 'Hesap oluştur',
    switchText: 'Zaten hesabın var mı?',
    switchLabel: 'Giriş yap',
    switchHref: '/login',
  },
} as const;

export function AuthForm({ mode }: { mode: Mode }) {
  const copy = COPY[mode];
  const { login, register } = useAuth();
  const router = useRouter();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setFormError(undefined);

    const parsed = schema.safeParse({ email, password });
    if (!parsed.success) {
      const errors: Record<string, string> = {};
      for (const issue of parsed.error.issues) {
        errors[String(issue.path[0])] = issue.message;
      }
      setFieldErrors(errors);
      return;
    }
    setFieldErrors({});
    setSubmitting(true);

    try {
      if (mode === 'login') {
        await login(parsed.data.email, parsed.data.password);
      } else {
        await register(parsed.data.email, parsed.data.password);
      }
      router.push('/dashboard');
    } catch (error) {
      setFormError(
        error instanceof ApiError
          ? error.message
          : 'Sunucuya ulaşılamadı. Backend çalışıyor mu?',
      );
      setSubmitting(false);
    }
  }

  return (
    <main id="main" className="flex flex-1 items-center justify-center px-4 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-6 text-center">
          <h1 className="text-title inline-flex items-center gap-2.5">
            <Logo size={22} />
            Code Review Agent
          </h1>
          <p className="text-muted mt-1 text-sm">
            Çok ajanlı kod inceleme ve güvenlik analizi
          </p>
        </div>

        <Card className="p-6">
          <h2 className="text-section mb-4">{copy.title}</h2>

          <form onSubmit={handleSubmit} className="flex flex-col gap-4" noValidate>
            {formError !== undefined && <Alert>{formError}</Alert>}

            <Field
              label="E-posta"
              name="email"
              type="email"
              autoComplete="email"
              required
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              error={fieldErrors.email}
            />
            <Field
              label="Parola"
              name="password"
              type="password"
              autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              error={fieldErrors.password}
              hint={mode === 'register' ? 'En az 8 karakter' : undefined}
            />

            <Button type="submit" variant="primary" disabled={submitting}>
              {submitting && <Spinner />}
              {copy.submit}
            </Button>
          </form>
        </Card>

        <p className="text-muted mt-4 text-center text-sm">
          {copy.switchText}{' '}
          <Link
            href={copy.switchHref}
            className="text-accent hover:text-accent-hover font-medium transition-colors hover:underline"
          >
            {copy.switchLabel}
          </Link>
        </p>
      </div>
    </main>
  );
}

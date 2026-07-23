/**
 * The handful of primitives this app needs.
 *
 * Hand-rolled rather than pulled from a component library: the surface is
 * small, and matching a pull-request review chrome is easier when the classes
 * are right here instead of behind another layer of variants.
 */

import type {
  ButtonHTMLAttributes,
  HTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from 'react';

import { cn } from '@/lib/utils';

type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
type ButtonSize = 'sm' | 'md';

// Indigo carries dark type, not white: #080B12 on #7C6BFF clears AA at 4.8:1
// where white would stall at 3.9:1.
const BUTTON_VARIANT: Record<ButtonVariant, string> = {
  primary:
    'bg-accent text-accent-contrast font-semibold border border-transparent hover:bg-accent-hover',
  secondary:
    'bg-surface-raised text-foreground border border-border-default hover:bg-surface-overlay hover:border-accent-ring',
  ghost:
    'bg-transparent text-muted border border-transparent hover:bg-surface-overlay hover:text-foreground',
  danger:
    'bg-danger-soft text-danger border border-danger-ring hover:bg-danger hover:text-accent-contrast',
};

const BUTTON_SIZE: Record<ButtonSize, string> = {
  sm: 'h-7 px-2.5 text-xs gap-1.5',
  md: 'h-9 px-3.5 text-sm gap-1.5',
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

export function Button({
  variant = 'secondary',
  size = 'md',
  className,
  ...props
}: ButtonProps) {
  return (
    <button
      className={cn(
        'inline-flex items-center justify-center rounded-md font-medium transition-colors',
        'disabled:cursor-not-allowed disabled:opacity-45',
        BUTTON_VARIANT[variant],
        BUTTON_SIZE[size],
        className,
      )}
      {...props}
    />
  );
}

const CONTROL_CLASS =
  'border-border-default bg-surface text-foreground h-9 rounded-md border px-3 text-sm ' +
  'transition-colors hover:border-accent-ring focus:border-accent focus:outline-none';

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  hint?: string;
  error?: string;
}

export function Field({ label, hint, error, id, className, ...props }: FieldProps) {
  const inputId = id ?? props.name ?? label;
  const describedBy = error !== undefined ? `${inputId}-error` : undefined;

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={inputId} className="text-sm font-medium">
        {label}
      </label>
      <input
        id={inputId}
        aria-invalid={error !== undefined}
        aria-describedby={describedBy}
        className={cn(
          CONTROL_CLASS,
          'placeholder:text-muted',
          error !== undefined && 'border-danger hover:border-danger',
          className,
        )}
        {...props}
      />
      {hint !== undefined && error === undefined && (
        <p className="text-muted text-xs">{hint}</p>
      )}
      {error !== undefined && (
        <p id={describedBy} className="text-danger text-xs">
          {error}
        </p>
      )}
    </div>
  );
}

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cn(CONTROL_CLASS, className)} {...props} />;
}

export function TextArea({
  className,
  ...props
}: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      className={cn(
        'code-surface border-border-default bg-code-background w-full rounded-md border p-3',
        'placeholder:text-muted placeholder:font-sans',
        'hover:border-accent-ring focus:border-accent transition-colors',
        className,
      )}
      {...props}
    />
  );
}

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        'border-border-default bg-surface-raised rounded-lg border',
        className,
      )}
      {...props}
    />
  );
}

export function Alert({
  tone = 'error',
  children,
}: {
  tone?: 'error' | 'info' | 'success';
  children: ReactNode;
}) {
  const tones = {
    error: 'border-danger-ring bg-danger-soft text-foreground',
    info: 'border-border-default bg-surface text-foreground',
    success: 'border-verified-ring bg-verified-soft text-foreground',
  };
  return (
    <div
      role={tone === 'error' ? 'alert' : 'status'}
      className={cn('rounded-md border px-3 py-2 text-sm', tones[tone])}
    >
      {children}
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      aria-hidden
      className={cn(
        'inline-block size-3.5 animate-spin rounded-full border-2 border-current border-t-transparent',
        className,
      )}
    />
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="border-border-default bg-surface/40 flex flex-col items-center gap-2 rounded-lg border border-dashed px-6 py-12 text-center">
      <p className="text-section">{title}</p>
      <p className="text-muted max-w-md text-sm">{description}</p>
      {action}
    </div>
  );
}
